import json

import pytest
from typer.testing import CliRunner

from texmodel import cli
from texmodel.targets import build_targets

runner = CliRunner()


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.texmodel]\nprefix = "t"\nimage = "img:1"\n'
        '[tool.texmodel.targets.card]\nsource = "card.tex"\n[tool.texmodel.targets.deck]\nsource = "deck.tex"\n'
    )
    for name in ("card", "deck", "other"):
        (tmp_path / f"{name}.tex").write_text("x")
    return tmp_path


def test_compile_human_output_and_exit_codes(toolchain, project):
    ok = runner.invoke(cli.app, ["compile", "card.tex"])
    assert ok.exit_code == 0 and "ok " in ok.stdout and "1 pages" in ok.stdout
    again = runner.invoke(cli.app, ["compile", "card.tex"])
    assert "[cache hit]" in again.stdout
    toolchain.log = (
        "./card.tex:2: Undefined control sequence.\nl.2 \\x\n(1 page)\nOutput written on card.pdf (1 page, 9 bytes).\n"
    )
    bad = runner.invoke(cli.app, ["compile", "card.tex", "--no-cache"])
    assert bad.exit_code == 1 and "TM-X010" in bad.stdout and "FAILED" in bad.stdout


def test_compile_json_and_options_reach_the_compiler(toolchain, project):
    result = runner.invoke(
        cli.app,
        [
            "compile",
            "card.tex",
            "--json",
            "--local",
            "--root",
            str(project),
            "--epoch",
            "5",
            "--passes",
            "2",
            "-o",
            "o",
        ],
    )
    data = json.loads(result.stdout)
    assert result.exit_code == 0 and data["image"] is None and data["pages"] == 1
    argv = next(c for c in toolchain.calls if "-interaction=nonstopmode" in c)
    assert "$max_repeat=2;" in argv and (project / "o" / "card.pdf").exists()


def test_diagnostics_show_a_location_and_a_repeat_count(toolchain, project):
    toolchain.log = (
        "Missing character: There is no x (U+0078) in font f!\n" * 2
        + "./card.tex:7: Boom\nOutput written on card.pdf (1 page, 9 bytes).\n"
    )
    out = runner.invoke(cli.app, ["compile", "card.tex"]).stdout
    assert "(x2)" in out and "./card.tex:7" in out


def test_missing_tools_exit_3_with_a_hint(toolchain, project):
    toolchain.image_missing = True
    result = runner.invoke(cli.app, ["compile", "card.tex"])
    assert result.exit_code == 3 and "TM-T002" in result.stderr and "hint: docker pull img:1" in result.stderr


def test_bad_config_exits_2(toolchain, project):
    (project / "pyproject.toml").write_text('[tool.texmodel]\nprefix = "t"\nbogus = 1\n')
    result = runner.invoke(cli.app, ["compile", "card.tex"])
    assert result.exit_code == 2 and "TM-D002" in result.stderr


def test_a_pyproject_without_a_texmodel_table_runs_on_the_host(toolchain, project):
    (project / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    assert runner.invoke(cli.app, ["compile", "card.tex"]).exit_code == 0
    assert not any(c[0] == "docker" for c in toolchain.calls)
    (project / "pyproject.toml").unlink()
    assert runner.invoke(cli.app, ["compile", "card.tex"]).exit_code == 0


def test_build_runs_declared_targets(toolchain, project):
    result = runner.invoke(cli.app, ["build", "-j", "2"])
    assert result.exit_code == 0 and "ok     card" in result.stdout and "ok     deck" in result.stdout
    assert (project / ".texmodel" / "build" / "deck" / "deck.pdf").exists()
    only = runner.invoke(cli.app, ["build", "deck"])
    assert "[cache hit]" in only.stdout and "card" not in only.stdout
    toolchain.log = "./deck.tex:1: Boom\n"
    assert runner.invoke(cli.app, ["build", "deck", "--local"]).exit_code == 1


def test_build_refuses_unknown_or_missing_targets(toolchain, project):
    unknown = runner.invoke(cli.app, ["build", "nope"])
    assert unknown.exit_code == 2 and "TM-D012" in unknown.stderr
    (project / "pyproject.toml").write_text('[tool.texmodel]\nprefix = "t"\n')
    none = runner.invoke(cli.app, ["build"])
    assert none.exit_code == 2 and "TM-D011" in none.stderr
    (project / "pyproject.toml").unlink()
    assert runner.invoke(cli.app, ["build"]).exit_code == 2


def test_build_targets_summary_lines(toolchain, project):
    from texmodel.compiler import Compiler
    from texmodel.config import Target

    summary = build_targets([Target(name="a", source="card.tex")], Compiler(), root=project, outdir=project / "o")
    assert summary.ok and summary.lines()[0].startswith("ok     a: 0 error(s), 1 page(s)")


def test_clean_command(toolchain, project):
    out = project / "o"
    out.mkdir()
    (out / "card.aux").write_text("")
    toolchain.latexmk_returncode = 1
    assert runner.invoke(cli.app, ["clean", "card.tex", "-o", "o", "--all", "--local"]).exit_code == 0
    assert not (out / "card.aux").exists()


def test_doctor_probes_the_configured_image(toolchain, project, monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)  # nothing on the host, the image is enough
    result = runner.invoke(cli.app, ["doctor"])
    assert (
        result.exit_code == 0 and "image   img:1: This is LuaHBTeX" in result.stdout and "latexmk 4.87" in result.stdout
    )
    assert "missing verapdf" in result.stdout and "no PDF/A checks" in result.stdout
    data = json.loads(runner.invoke(cli.app, ["doctor", "--json"]).stdout)
    assert data["image"]["ok"] and data["image"]["missing"] == [{"name": "verapdf", "gap": cli.TOOLS["verapdf"]}]
    assert data["image"]["revision"] == "deadbeefcafe"


def test_doctor_reports_an_unusable_image(toolchain, project, monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/bin/{name}")
    toolchain.image_missing = True
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 3 and "image   img:1:" in result.stdout and "docker pull img:1" in result.stdout
    assert json.loads(runner.invoke(cli.app, ["doctor", "--json"]).stdout)["image"]["ok"] is False
