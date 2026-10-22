import json
import pathlib

import pytest

from texmodel.errors import DeclarationError
from texmodel.plan import Line, Plan
from texmodel_build import (
    compiler as compiler_module,
    diagnostics as d,
)
from texmodel_build._internal import spawn as spawn_module
from texmodel_build._internal.spawn import Proc
from texmodel_build.compiler import Compiler
from texmodel_build.errors import CompileError, ToolchainError
from texmodel_build.result import CompileResult

from .conftest import OK_LOG, FakeToolchain


@pytest.fixture
def src(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "doc").mkdir()
    (tmp_path / "doc" / "a.tex").write_text("\\documentclass{article}")
    return tmp_path / "doc" / "a.tex"


def latexmk_call(fake: FakeToolchain) -> list[str]:
    return next(c for c in fake.calls if "-interaction=nonstopmode" in c)


def test_local_compile_builds_a_safe_argv_in_the_source_dir(toolchain, src, tmp_path):
    result = Compiler(max_passes=3, epoch=1700000000).compile(src, tmp_path / "out")
    assert result.ok and result.pages == 1 and result.passes == 1 and result.image is None
    argv = latexmk_call(toolchain)
    assert argv[0] == "latexmk" and argv[-1] == "a.tex"
    assert "-pdflatex=lualatex --no-shell-escape %O %S" in argv
    assert f"-outdir={tmp_path / 'out'}" in argv and "$max_repeat=3;" in argv and "-file-line-error" in argv
    assert (result.engine, result.latexmk_version) == ("lualatex", "4.87")
    assert result.engine_version.startswith("This is LuaHBTeX")


def test_container_compile_mounts_sources_read_only_and_runs_as_the_user(toolchain, src, tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    comp = Compiler(image="img:1", roots=(root,), font_cache=tmp_path / "fonts")
    result = comp.compile(src, tmp_path / "out")
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


def test_output_dir_sharing_the_source_dir_is_refused_but_a_subdir_is_fine(toolchain, src):
    for bad in (src.parent, src.parent.parent):
        with pytest.raises(DeclarationError) as info:
            Compiler().compile(src, bad)
        assert info.value.code == "TM-X002"
    assert Compiler().compile(src, src.parent / ".texmodel" / "build").ok
    with pytest.raises(DeclarationError) as info:
        Compiler().compile(src.parent / "missing.tex", src.parent.parent / "o")
    assert info.value.code == "TM-X001"


def test_a_comma_in_a_mounted_path_is_refused(toolchain, tmp_path):
    odd = tmp_path / "a,b"
    odd.mkdir()
    (odd / "a.tex").write_text("")
    with pytest.raises(DeclarationError) as info:
        Compiler(image="img").compile(odd / "a.tex", tmp_path / "out")
    assert info.value.code == "TM-X003"


def test_errors_in_the_log_make_the_result_not_ok_and_raise_for_status_carries_them(toolchain, src, tmp_path):
    toolchain.log = "./a.tex:3: Undefined control sequence.\nl.3 \\foo\n" + OK_LOG
    toolchain.returncode = 12
    result = Compiler().compile(src, tmp_path / "out")
    assert not result.ok and result.pdf is not None
    assert [type(x) for x in result.diagnostics] == [d.UndefinedControlSequence]
    with pytest.raises(CompileError) as info:
        result.raise_for_status()
    assert info.value.code == "TM-X010" and info.value.diagnostics == result.diagnostics


def test_diagnostics_in_the_source_carry_the_path_of_the_plan_line_behind_them(toolchain, src, tmp_path):
    plan = Plan((Line("header", "%"), Line("Card[0]", "\\a"), Line("Card[1]", "\\foo")))
    toolchain.log = (
        "./a.tex:3: Undefined control sequence.\nl.3 \\foo\n"
        "res/x.sty:2: Undefined control sequence.\nl.2 \\bar\n"
        "./a.tex:99: Undefined control sequence.\nl.99 \\far\n"
        "Package pk Warning: Card 'X' does not fit.\n(pk)   More on input line 2.\n" + OK_LOG
    )
    toolchain.returncode = 12
    paths = {
        (x.name if isinstance(x, d.UndefinedControlSequence) else x.message[:6]): x.path
        for x in Compiler().compile(src, tmp_path / "out", plan=plan).diagnostics
    }
    assert paths == {"\\foo": "Card[1]", "\\bar": None, "\\far": None, "Card '": "Card[0]"}
    assert all(x.path is None for x in Compiler().compile(src, tmp_path / "out2").diagnostics)


def test_an_overset_carries_the_path_of_the_plan_line_behind_it(toolchain, src, tmp_path):
    plan = Plan((Line("header", "%"), Line("Card[0]", "\\a")))
    toolchain.log = "Package pk Warning: Card 'X' does not fit 3pt 1pt on input line 2.\n" + OK_LOG
    rule = d.Measure.declare("fit", "pk", r"Card '(?P<item>X)' does not fit (?P<needs>\S+) (?P<has>\S+)")
    result = Compiler(measures=(rule,)).compile(src, tmp_path / "out", plan=plan)
    (over,) = (x for x in result.diagnostics if isinstance(x, d.Overset))
    assert (over.path, over.over_pt) == ("Card[0]", 2.0) and not result.ok
    assert CompileResult.from_dict(result.to_dict()) == result


def test_failure_without_a_diagnosable_error_is_never_silent(toolchain, src, tmp_path):
    toolchain.log = None
    toolchain.write_pdf = False
    toolchain.returncode = 12
    result = Compiler().compile(src, tmp_path / "out")
    assert not result.ok and result.pdf is None and result.log is None
    (only,) = result.diagnostics
    assert isinstance(only, d.Unexplained) and "exited 12" in only.message
    with pytest.raises(CompileError) as info:
        result.raise_for_status()
    assert info.value.code == "TM-X099"


def test_stale_output_from_an_earlier_run_is_not_reported_as_this_runs(toolchain, src, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    old = out / "a.log"
    old.write_text(OK_LOG)
    import os

    os.utime(old, (1, 1))
    toolchain.log = None
    toolchain.write_pdf = False
    result = Compiler().compile(src, out)
    assert result.log is None and result.pdf is None and not result.ok


def test_timeout_is_a_result_and_kills_the_container(toolchain, src, tmp_path):
    toolchain.timed_out = True
    comp = Compiler(image="img", timeout=7)
    result = comp.compile(src, tmp_path / "out")
    assert not result.ok and "timed out after 7s" in result.diagnostics[0].message
    assert any(c[:2] == ["docker", "kill"] for c in toolchain.calls)


def test_non_convergence_reports_the_aux_entries_that_still_move(toolchain, src, tmp_path):
    toolchain.stdout = (
        "Run number 3 of rule 'pdflatex'\nLatexmk: Maximum runs of pdflatex reached without getting stable files\n"
    )
    result = Compiler(max_passes=3).compile(src, tmp_path / "out")
    (note,) = [x for x in result.diagnostics if isinstance(x, d.NotConverged)]
    assert note.code == "TM-X030" and note.changed == ("k",) and "k" in note.message
    assert result.passes == 3 and toolchain.runs == 2  # the compile, and one more pass to see what moves
    assert any("-g" in c for c in toolchain.calls)


def test_non_convergence_with_no_visible_aux_change(toolchain, src, tmp_path, monkeypatch):
    toolchain.stdout = "Maximum runs of pdflatex reached without getting stable files\n"
    monkeypatch.setattr(compiler_module, "aux_diff", lambda a, b: ())
    result = Compiler().compile(src, tmp_path / "out")
    assert "nothing in .aux" in next(x for x in result.diagnostics if isinstance(x, d.NotConverged)).message


@pytest.mark.parametrize(("code", "image"), [(127, None), (127, "img"), (125, "img")])
def test_a_missing_tool_is_a_toolchain_error(toolchain, src, tmp_path, code, image):
    toolchain.returncode = code
    with pytest.raises(ToolchainError) as info:
        Compiler(image=image).compile(src, tmp_path / "out")
    assert info.value.code == "TM-T004"


def test_missing_image_and_missing_latexmk_are_toolchain_errors(toolchain, src, tmp_path):
    toolchain.image_missing = True
    with pytest.raises(ToolchainError) as info:
        Compiler(image="nope").check_ready()
    assert info.value.code == "TM-T002" and "docker pull nope" in info.value.hint
    toolchain.image_missing = False
    toolchain.probe = "sh: latexmk: not found\n@@\nThis is LuaHBTeX\n@@\n"
    with pytest.raises(ToolchainError) as info:
        Compiler(image="img").check_ready()
    assert info.value.code == "TM-T003" and "image img" in str(info.value)
    with pytest.raises(ToolchainError):
        Compiler().check_ready()


def test_a_failing_probe_is_a_toolchain_error(monkeypatch, src, tmp_path):
    monkeypatch.setattr(compiler_module, "spawn", lambda argv, **kw: Proc(2, "", "boom"))
    with pytest.raises(ToolchainError) as info:
        Compiler().check_ready()
    assert info.value.code == "TM-T005"


def test_probe_reports_which_optional_tools_the_image_has(toolchain):
    versions = Compiler(image="img").check_ready()
    assert versions.tools == ("kpsewhich", "gs") and versions.latexmk_version == "4.87"


def test_clean_uses_latexmk_and_falls_back_to_deleting_known_files(toolchain, src, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    for ext in ("aux", "log", "pdf", "txt"):
        (out / f"a.{ext}").write_text("")
    Compiler().clean(src, out)
    assert "-c" in toolchain.calls[-1] and (out / "a.aux").exists()  # latexmk did it, we deleted nothing
    toolchain.latexmk_returncode = 12  # latexmk cannot clean: delete the intermediates ourselves, keep the PDF
    Compiler().clean(src, out)
    assert not (out / "a.aux").exists() and not (out / "a.log").exists() and (out / "a.pdf").exists()
    Compiler().clean(src, out, everything=True)
    assert "-C" in toolchain.calls[-1] and not (out / "a.pdf").exists() and (out / "a.txt").exists()


def test_clean_falls_back_when_latexmk_cannot_run_at_all(monkeypatch, src, tmp_path):
    def boom(argv, **kw):
        raise ToolchainError("x", code="TM-T001")

    monkeypatch.setattr(compiler_module, "spawn", boom)
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.aux").write_text("")
    Compiler().clean(src, out)
    assert not (out / "a.aux").exists()


def test_the_real_spawn_runs_argv_without_a_shell_and_reports_timeouts_and_missing_programs(tmp_path):
    ok = spawn_module.spawn(
        ["python3", "-c", "print('hi')"], cwd=tmp_path, env={"PATH": "/usr/bin:/bin:/usr/local/bin"}, timeout=30
    )
    assert ok.returncode == 0 and ok.stdout.strip() == "hi" and not ok.timed_out
    slow = spawn_module.spawn(["sleep", "5"], cwd=None, env={"PATH": "/bin:/usr/bin"}, timeout=0.2)
    assert slow.timed_out and slow.returncode == -1
    with pytest.raises(ToolchainError) as info:
        spawn_module.spawn(["texmodel-no-such-program"], cwd=None, env={}, timeout=5)
    assert info.value.code == "TM-T001"
    assert spawn_module.text(b"ab") == "ab" and spawn_module.text(None) == ""


def test_result_round_trips_as_json(toolchain, src, tmp_path):
    result = Compiler(image="img").compile(src, tmp_path / "out")
    from texmodel_build.result import CompileResult

    assert CompileResult.from_dict(json.loads(json.dumps(result.to_dict()))) == result
    assert result.probes == {} and result.errors == ()
    result.raise_for_status()


def test_probes_are_measurements_in_the_log(toolchain, src, tmp_path):
    toolchain.log = "texmodel:probe:fact.height=11.2mm\n" + OK_LOG
    result = Compiler().compile(src, tmp_path / "out")
    assert result.ok and result.probes == {"fact.height": "11.2mm"} and result.probe("fact.height") == "11.2mm"


def test_font_dirs_become_osfontdir_and_halt_on_error_a_flag(toolchain, src, tmp_path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    local = Compiler(font_dirs=(fonts,), halt_on_error=True)
    local.compile(src, tmp_path / "o1")
    argv = latexmk_call(toolchain)
    assert "-halt-on-error" in argv
    boxed = Compiler(image="img", font_dirs=(fonts,)).compile(src, tmp_path / "o2")
    assert boxed.ok
    call = [c for c in toolchain.calls if "-interaction=nonstopmode" in c][-1]
    assert "OSFONTDIR=/work/fonts/0" in " ".join(call) and "-halt-on-error" not in call
    assert any("target=/work/fonts/0" in a and a.endswith("readonly") for a in call)


def test_recompiling_into_an_up_to_date_outdir_is_still_ok(toolchain, src, tmp_path):
    toolchain.up_to_date = True
    comp = Compiler()
    first = comp.compile(src, tmp_path / "out")
    again = comp.compile(src, tmp_path / "out")  # latexmk runs no pass: nothing changed
    assert toolchain.runs == 1 and again.passes == 0
    assert again.ok and again.pdf == first.pdf and again.pages == first.pages
    assert again.diagnostics == first.diagnostics
