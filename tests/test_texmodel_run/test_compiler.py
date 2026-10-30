import asyncio
import json
import os
import pathlib
import subprocess
import time

import pytest

from texmodel.errors import DeclarationError
from texmodel.plan import Line, Plan
from texmodel.run import (
    compiler as compiler_module,
    diagnostics as d,
)
from texmodel.run._internal import spawn as spawn_module
from texmodel.run._internal.spawn import Proc
from texmodel.run.compiler import Compiler
from texmodel.run.errors import CompileError, ToolchainError
from texmodel.run.result import CompileResult

from .conftest import OK_LOG, FakeToolchain


@pytest.fixture
def src(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "doc").mkdir()
    (tmp_path / "doc" / "a.tex").write_text("\\documentclass{article}")
    return tmp_path / "doc" / "a.tex"


def latexmk_call(fake: FakeToolchain) -> list[str]:
    return next(c for c in fake.calls if "-interaction=nonstopmode" in c)


async def test_local_compile_builds_a_safe_argv_in_the_source_dir(toolchain, src, tmp_path):
    result = await Compiler(max_passes=3, epoch=1700000000).compile(src, tmp_path / "out")
    assert result.ok and result.pages == 1 and result.passes == 1 and result.image is None
    argv = latexmk_call(toolchain)
    assert argv[0] == "latexmk" and argv[-1] == "a.tex"
    assert "-pdflatex=lualatex --no-shell-escape %O %P" in argv  # %P: the file marks, then \\input of the source
    assert any(a.startswith("-pretex=\\directlua{") and "texmodel:open:<" in a for a in argv)
    assert f"-outdir={tmp_path / 'out'}" in argv and "$max_repeat=3;" in argv and "-file-line-error" in argv
    assert (result.engine, result.latexmk_version) == ("lualatex", "4.87")
    assert result.engine_version.startswith("This is LuaHBTeX")


async def test_container_compile_mounts_sources_read_only_and_runs_as_the_user(toolchain, src, tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    comp = Compiler(image="img:1", roots=(root,), font_cache=tmp_path / "fonts")
    result = await comp.compile(src, tmp_path / "out")
    assert result.ok and result.image == "img:1" and result.image_revision == "deadbeefcafe"
    assert result.image_digest and result.image_digest.startswith("sha256:")
    argv = latexmk_call(toolchain)
    joined = " ".join(argv)
    assert "--user" in argv and "-w /work/src" in joined and "--rm" in argv
    assert not {"--network", "--read-only", "--cap-drop", "--memory"} & set(argv)  # the image is the environment
    assert "--entrypoint latexmk img:1" in joined
    mounts = [a for a in argv if a.startswith("type=bind")]
    assert any("target=/work/src" in m and m.endswith("readonly") for m in mounts)
    assert any("target=/work/roots/0" in m and m.endswith("readonly") for m in mounts)
    assert any("target=/work/out" in m and not m.endswith("readonly") for m in mounts)
    assert any("target=/cache" in m and not m.endswith("readonly") for m in mounts)
    assert "TEXINPUTS=.:/work/roots/0:" in argv and "TEXMFVAR=/cache" in argv and "-outdir=/work/out" in argv
    assert (tmp_path / "fonts" / ("ab" * 6)).is_dir()  # one font cache per image


async def test_output_dir_sharing_the_source_dir_is_refused_but_a_subdir_is_fine(toolchain, src):
    for bad in (src.parent, src.parent.parent):
        with pytest.raises(DeclarationError) as info:
            await Compiler().compile(src, bad)
        assert info.value.code == "TM-X002"
    assert (await Compiler().compile(src, src.parent / ".texmodel" / "build")).ok
    with pytest.raises(DeclarationError) as info:
        await Compiler().compile(src.parent / "missing.tex", src.parent.parent / "o")
    assert info.value.code == "TM-X001"


async def test_a_comma_in_a_mounted_path_is_refused(toolchain, tmp_path):
    odd = tmp_path / "a,b"
    odd.mkdir()
    (odd / "a.tex").write_text("")
    with pytest.raises(DeclarationError) as info:
        await Compiler(image="img").compile(odd / "a.tex", tmp_path / "out")
    assert info.value.code == "TM-X003"


async def test_errors_in_the_log_make_the_result_not_ok_and_raise_for_status_carries_them(toolchain, src, tmp_path):
    toolchain.log = "./a.tex:3: Undefined control sequence.\nl.3 \\foo\n" + OK_LOG
    toolchain.returncode = 12
    result = await Compiler().compile(src, tmp_path / "out")
    assert not result.ok and result.pdf is not None
    assert [type(x) for x in result.diagnostics] == [d.UndefinedControlSequence]
    with pytest.raises(CompileError) as info:
        result.raise_for_status()
    assert info.value.code == "TM-X010" and info.value.diagnostics == result.diagnostics


async def test_diagnostics_in_the_source_carry_the_path_of_the_plan_line_behind_them(toolchain, src, tmp_path):
    plan = Plan((Line("header", "%"), Line("Card[0]", "\\a"), Line("Card[1]", "\\foo")))
    toolchain.log = (
        "./a.tex:3: Undefined control sequence.\nl.3 \\foo\n"
        "res/x.sty:2: Undefined control sequence.\nl.2 \\bar\n"
        "./a.tex:99: Undefined control sequence.\nl.99 \\far\n"
        "texmodel:open:<./a.tex>\n(./a.tex\n"
        "Package pk Warning: Card 'X' does not fit.\n(pk)   More on input line 2.\n"
        ")\ntexmodel:close\n" + OK_LOG
    )
    toolchain.returncode = 12
    paths = {
        (x.name if isinstance(x, d.UndefinedControlSequence) else x.message[:6]): x.path
        for x in (await Compiler().compile(src, tmp_path / "out", plan=plan)).diagnostics
    }
    assert paths == {"\\foo": "Card[1]", "\\bar": None, "\\far": None, "Card '": "Card[0]"}
    assert all(x.path is None for x in (await Compiler().compile(src, tmp_path / "out2")).diagnostics)


async def test_plans_of_other_files_locate_the_diagnostics_in_them_by_file_name(toolchain, src, tmp_path):
    sty = Plan((Line("header", "%"), Line("sizing", "\\fp_nosuch:n")))
    toolchain.log = (
        "./a.tex:3: Undefined control sequence.\nl.3 \\foo\n./x.sty:2: Undefined control sequence.\nl.2 \\bar\n"
        + OK_LOG
    )
    toolchain.returncode = 12
    found = (await Compiler().compile(src, tmp_path / "out", plans={"x.sty": sty})).diagnostics
    assert {x.name: x.path for x in found if isinstance(x, d.UndefinedControlSequence)} == {
        "\\foo": None,
        "\\bar": "sizing",
    }


async def test_a_line_is_placed_in_the_file_open_where_the_log_reports_it(toolchain, src, tmp_path):
    """`on input line N` names no file: the engine's file marks say which. A warning raised in an `\\input` part, or in
    a package while it loads, is not placed on line N of the source; one the log places in no file is not placed."""
    plan = Plan((Line("header", "%"), Line("Card[0]", "\\a"), Line("Card[1]", "\\b")))
    toolchain.log = (
        "Package pk Warning: before any file on input line 2.\n"
        "texmodel:open:<./a.tex>\n(./a.tex\n"
        "texmodel:open:<./pk.sty>\n(./pk.sty\nPackage pk Warning: loading on input line 2.\n)\ntexmodel:close\n"
        "Package pk Warning: in the source on input line 3.\n"
        "texmodel:open:<./part.tex>\n(./part.tex\nPackage pk Warning: in the part on input line 2.\n"
        "Overfull \\hbox (1.0pt too wide) in paragraph at lines 2--2\n)\ntexmodel:close\n"
        "Package pk Warning: back in the source on input line 2.\n"
        ")\ntexmodel:close\n" + OK_LOG
    )
    found = {
        x.message: (x.file, x.path)
        for x in (await Compiler().compile(src, tmp_path / "out", plan=plan)).diagnostics
        if x.line
    }
    assert found == {
        "before any file": (None, None),
        "loading": ("./pk.sty", None),
        "in the source": ("./a.tex", "Card[1]"),
        "in the part": ("./part.tex", None),
        "Overfull \\hbox (1.0pt too wide) in paragraph at lines 2--2": ("./part.tex", None),
        "back in the source": ("./a.tex", "Card[0]"),
    }


async def test_an_overset_carries_the_path_of_the_plan_line_behind_it(toolchain, src, tmp_path):
    plan = Plan((Line("header", "%"), Line("Card[0]", "\\a")))
    toolchain.log = (
        "texmodel:open:<./a.tex>\nPackage pk Warning: Card 'X' does not fit 3pt 1pt on input line 2.\n"
        "texmodel:close\n" + OK_LOG
    )
    rule = d.Measure.declare("fit", "pk", r"Card '(?P<item>X)' does not fit (?P<needs>\S+) (?P<has>\S+)")
    result = await Compiler(measures=(rule,)).compile(src, tmp_path / "out", plan=plan)
    (over,) = (x for x in result.diagnostics if isinstance(x, d.Overset))
    assert (over.path, over.over_pt) == ("Card[0]", 2.0) and not result.ok
    assert CompileResult.from_dict(result.to_dict()) == result


async def test_failure_without_a_diagnosable_error_is_never_silent(toolchain, src, tmp_path):
    toolchain.log = None
    toolchain.write_pdf = False
    toolchain.returncode = 12
    result = await Compiler().compile(src, tmp_path / "out")
    assert not result.ok and result.pdf is None and result.log is None
    (only,) = result.diagnostics
    assert isinstance(only, d.Unexplained) and "exited 12" in only.message
    with pytest.raises(CompileError) as info:
        result.raise_for_status()
    assert info.value.code == "TM-X099"


async def test_stale_output_from_an_earlier_run_is_not_reported_as_this_runs(toolchain, src, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    old = out / "a.log"
    old.write_text(OK_LOG)
    import os

    os.utime(old, (1, 1))
    toolchain.log = None
    toolchain.write_pdf = False
    result = await Compiler().compile(src, out)
    assert result.log is None and result.pdf is None and not result.ok


async def test_timeout_is_a_result_and_kills_the_container(toolchain, src, tmp_path):
    toolchain.timed_out = True
    comp = Compiler(image="img", timeout=7)
    result = await comp.compile(src, tmp_path / "out")
    assert not result.ok and "timed out after 7s" in result.diagnostics[0].message
    assert any(c[:2] == ["docker", "kill"] for c in toolchain.calls)


async def test_non_convergence_reports_the_aux_entries_that_still_move(toolchain, src, tmp_path):
    toolchain.stdout = (
        "Run number 3 of rule 'pdflatex'\nLatexmk: Maximum runs of pdflatex reached without getting stable files\n"
    )
    result = await Compiler(max_passes=3).compile(src, tmp_path / "out")
    (note,) = [x for x in result.diagnostics if isinstance(x, d.NotConverged)]
    assert note.code == "TM-X030" and note.changed == ("k",) and "k" in note.message
    assert result.passes == 3 and toolchain.runs == 2  # the compile, and one more pass to see what moves
    assert any("-g" in c for c in toolchain.calls)


async def test_non_convergence_with_no_visible_aux_change(toolchain, src, tmp_path, monkeypatch):
    toolchain.stdout = "Maximum runs of pdflatex reached without getting stable files\n"
    monkeypatch.setattr(compiler_module, "aux_diff", lambda a, b: ())
    result = await Compiler().compile(src, tmp_path / "out")
    assert "nothing in .aux" in next(x for x in result.diagnostics if isinstance(x, d.NotConverged)).message


@pytest.mark.parametrize(
    ("code", "image", "who"),
    [(127, None, "could not run latexmk"), (127, "img", "could not run latexmk"), (125, "img", "docker could not")],
)
async def test_a_missing_tool_is_a_toolchain_error(toolchain, src, tmp_path, code, image, who):
    toolchain.returncode = code
    with pytest.raises(ToolchainError) as info:
        await Compiler(image=image).compile(src, tmp_path / "out")
    assert info.value.code == "TM-T004" and str(info.value).startswith(who)


async def test_missing_image_and_missing_latexmk_are_toolchain_errors(toolchain, src, tmp_path):
    toolchain.image_missing = True
    with pytest.raises(ToolchainError) as info:
        await Compiler(image="nope").check_ready()
    assert info.value.code == "TM-T002" and "docker pull nope" in info.value.hint
    toolchain.image_missing = False
    toolchain.probe = "sh: latexmk: not found\n@@\nThis is LuaHBTeX\n@@\n"
    with pytest.raises(ToolchainError) as info:
        await Compiler(image="img").check_ready()
    assert info.value.code == "TM-T003" and "image img" in str(info.value)
    with pytest.raises(ToolchainError):
        await Compiler().check_ready()


async def test_a_failing_probe_is_a_toolchain_error(monkeypatch, src, tmp_path):
    async def failing(argv, **kw):
        return Proc(2, "", "boom")

    monkeypatch.setattr(compiler_module, "spawn", failing)
    with pytest.raises(ToolchainError) as info:
        await Compiler().check_ready()
    assert info.value.code == "TM-T005"


async def test_probe_reports_which_optional_tools_the_image_has(toolchain):
    versions = await Compiler(image="img").check_ready()
    assert versions.tools == ("kpsewhich", "gs") and versions.latexmk_version == "4.87"


async def test_clean_uses_latexmk_and_falls_back_to_deleting_known_files(toolchain, src, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    for ext in ("aux", "log", "pdf", "txt"):
        (out / f"a.{ext}").write_text("")
    await Compiler().clean(src, out)
    assert "-c" in toolchain.calls[-1] and (out / "a.aux").exists()  # latexmk did it, we deleted nothing
    toolchain.latexmk_returncode = 12  # latexmk cannot clean: delete the intermediates ourselves, keep the PDF
    await Compiler().clean(src, out)
    assert not (out / "a.aux").exists() and not (out / "a.log").exists() and (out / "a.pdf").exists()
    await Compiler().clean(src, out, everything=True)
    assert "-C" in toolchain.calls[-1] and not (out / "a.pdf").exists() and (out / "a.txt").exists()


async def test_clean_falls_back_when_latexmk_cannot_run_at_all(monkeypatch, src, tmp_path):
    async def boom(argv, **kw):
        raise ToolchainError("x", code="TM-T001")

    monkeypatch.setattr(compiler_module, "spawn", boom)
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.aux").write_text("")
    await Compiler().clean(src, out)
    assert not (out / "a.aux").exists()


async def test_the_real_spawn_runs_argv_without_a_shell_and_reports_timeouts_and_missing_programs(tmp_path):
    ok = await spawn_module.spawn(
        ["python3", "-c", "print('hi')"], cwd=tmp_path, env={"PATH": "/usr/bin:/bin:/usr/local/bin"}, timeout=30
    )
    assert ok.returncode == 0 and ok.stdout.strip() == "hi" and not ok.timed_out
    script = "import sys, time; print('started', flush=True); time.sleep(5)"
    slow = await spawn_module.spawn(["python3", "-c", script], cwd=None, env={"PATH": "/usr/bin:/bin"}, timeout=0.5)
    assert slow.timed_out and slow.returncode == -1 and slow.stdout == "started\n"  # what it wrote is kept
    with pytest.raises(ToolchainError) as info:
        await spawn_module.spawn(["texmodel-no-such-program"], cwd=None, env={}, timeout=5)
    assert info.value.code == "TM-T001"
    assert spawn_module.text(b"ab") == "ab"


async def test_a_cancelled_spawn_kills_its_process_before_it_re_raises(tmp_path):
    pid_file = tmp_path / "pid"
    script = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(30)"
    task = asyncio.create_task(
        spawn_module.spawn(["python3", "-c", script], cwd=None, env={"PATH": "/usr/bin:/bin"}, timeout=60)
    )
    while not pid_file.is_file() or not pid_file.read_text():
        await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(ProcessLookupError):  # killed and reaped: no such process any more
        os.kill(int(pid_file.read_text()), 0)


def gone(pid: int) -> bool:
    """No such process, or one already dead and waiting to be reaped by init (a zombie)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False).stdout
    return state.strip().startswith("Z")


@pytest.mark.parametrize("stop", ["cancel", "timeout"])
async def test_a_stopped_spawn_kills_what_its_process_started(tmp_path, stop):
    """latexmk starts the engine: stopping the spawn stops both, and does not wait for the engine to end."""
    pid_file = tmp_path / "pid"
    script = f"sleep 30 & echo $! > {pid_file}; wait"
    started = time.monotonic()
    task = asyncio.create_task(
        spawn_module.spawn(
            ["sh", "-c", script], cwd=None, env={"PATH": "/usr/bin:/bin"}, timeout=1 if stop == "timeout" else 60
        )
    )
    while not pid_file.is_file() or not pid_file.read_text().strip():
        await asyncio.sleep(0.05)
    if stop == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        assert (await task).timed_out
    assert time.monotonic() - started < 10
    child = int(pid_file.read_text())
    for _ in range(50):  # an orphan is reaped by init, not by us
        if gone(child):
            break
        await asyncio.sleep(0.05)
    assert gone(child)


async def test_a_cancelled_or_timed_out_run_in_the_image_kills_its_container(toolchain, monkeypatch, src, tmp_path):
    started = asyncio.Event()

    async def hangs(argv, **kw):
        if argv[:2] == ["docker", "run"] and "-interaction=nonstopmode" in argv:
            toolchain.calls.append(list(argv))
            started.set()
            await asyncio.sleep(30)
        return await toolchain(argv, **kw)

    monkeypatch.setattr(compiler_module, "spawn", hangs)
    task = asyncio.create_task(Compiler(image="img").compile(src, tmp_path / "out"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    name = latexmk_call(toolchain)[latexmk_call(toolchain).index("--name") + 1]
    assert toolchain.calls[-1] == ["docker", "kill", name]
    monkeypatch.setattr(compiler_module, "spawn", toolchain)
    toolchain.timed_out = True
    await Compiler(image="img").compile(src, tmp_path / "out2")
    assert toolchain.calls[-1][:2] == ["docker", "kill"]


async def test_result_round_trips_as_json(toolchain, src, tmp_path):
    result = await Compiler(image="img").compile(src, tmp_path / "out")
    from texmodel.run.result import CompileResult

    assert CompileResult.from_dict(json.loads(json.dumps(result.to_dict()))) == result
    assert result.probes == {} and result.errors == ()
    result.raise_for_status()


async def test_probes_are_measurements_in_the_log(toolchain, src, tmp_path):
    toolchain.log = "texmodel:probe:fact.height=11.2mm\n" + OK_LOG
    result = await Compiler().compile(src, tmp_path / "out")
    assert result.ok and result.probes == {"fact.height": "11.2mm"} and result.probe("fact.height") == "11.2mm"


async def test_font_dirs_become_osfontdir_and_halt_on_error_a_flag(toolchain, src, tmp_path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    local = Compiler(font_dirs=(fonts,), halt_on_error=True)
    await local.compile(src, tmp_path / "o1")
    argv = latexmk_call(toolchain)
    assert "-halt-on-error" in argv
    boxed = await Compiler(image="img", font_dirs=(fonts,)).compile(src, tmp_path / "o2")
    assert boxed.ok
    call = [c for c in toolchain.calls if "-interaction=nonstopmode" in c][-1]
    assert "OSFONTDIR=/work/fonts/0" in " ".join(call) and "-halt-on-error" not in call
    assert any("target=/work/fonts/0" in a and a.endswith("readonly") for a in call)


async def test_recompiling_into_an_up_to_date_outdir_is_still_ok(toolchain, src, tmp_path):
    toolchain.up_to_date = True
    comp = Compiler()
    first = await comp.compile(src, tmp_path / "out")
    again = await comp.compile(src, tmp_path / "out")  # latexmk runs no pass: nothing changed
    assert toolchain.runs == 1 and again.passes == 0
    assert again.ok and again.pdf == first.pdf and again.pages == first.pages
    assert again.diagnostics == first.diagnostics
