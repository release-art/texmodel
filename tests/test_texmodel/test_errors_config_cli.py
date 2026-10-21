import json
import logging

import pytest
from typer.testing import CliRunner

from texmodel import cli, errors
from texmodel.config import Config, Target, load_config

runner = CliRunner()


def test_every_error_is_a_texmodel_error_with_code_path_hint():
    for name in (
        "DeclarationError",
        "ValidationError",
        "CompileError",
        "VerifyError",
        "MigrationError",
        "ToolchainError",
    ):
        exc = getattr(errors, name)("boom", code="TM-X1", path="a[0]", hint="fix")
        assert isinstance(exc, errors.TexmodelError)
        assert (exc.code, exc.path, exc.hint) == ("TM-X1", "a[0]", "fix")


def test_load_config(tmp_path):
    f = tmp_path / "pyproject.toml"
    f.write_text('[tool.texmodel]\nprefix = "ac"\n')
    assert load_config(f) == Config(prefix="ac")


@pytest.mark.parametrize(
    ("body", "code"),
    [("", "TM-D001"), ('[tool.texmodel]\nprefix = "a"\nbogus = 1\n', "TM-D002"), ("[tool.texmodel]\n", "TM-D003")],
)
def test_load_config_refuses(tmp_path, body, code):
    f = tmp_path / "pyproject.toml"
    f.write_text(body)
    with pytest.raises(errors.DeclarationError) as info:
        load_config(f)
    assert info.value.code == code


def test_doctor_exit_3_when_required_tool_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    result = runner.invoke(cli.app, ["doctor", "--json"])
    assert result.exit_code == 3
    assert {t["name"] for t in json.loads(result.output)["tools"]} == set(cli.TOOLS)


def test_doctor_ok_when_tools_present(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/bin/{name}")
    assert runner.invoke(cli.app, ["doctor"]).exit_code == 0


def test_version():
    assert runner.invoke(cli.app, ["version"]).exit_code == 0


def test_verbose_logs_to_stderr_not_stdout(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    log = logging.getLogger("texmodel")
    monkeypatch.setattr(log, "handlers", list(log.handlers))
    monkeypatch.setattr(log, "level", log.level)
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/bin/{name}")
    result = runner.invoke(cli.app, ["-vv", "doctor", "--json"])
    assert "DEBUG texmodel.cli: probe lualatex -> /bin/lualatex" in result.stderr
    assert json.loads(result.stdout)  # stdout is still clean JSON
    assert log.level == logging.DEBUG
    assert runner.invoke(cli.app, ["-v", "version"]).exit_code == 0
    assert log.level == logging.INFO


def test_targets_are_read_from_config(tmp_path):
    f = tmp_path / "pyproject.toml"
    f.write_text(
        '[tool.texmodel]\nprefix = "ac"\nimage = "img:1"\n[tool.texmodel.targets.card]\nsource = "card.tex"\n'
        '[tool.texmodel.targets.deck]\nsource = "deck.tex"\nvariant = "print"\nprofile = "pdfx4"\n'
    )
    config = load_config(f)
    assert config.image == "img:1" and set(config.targets) == {"card", "deck"}
    assert config.targets["deck"] == Target(name="deck", source="deck.tex", variant="print", profile="pdfx4")


def test_a_bad_target_is_a_declaration_error(tmp_path):
    f = tmp_path / "pyproject.toml"
    f.write_text('[tool.texmodel]\nprefix = "a"\n[tool.texmodel.targets.x]\nbogus = 1\n')
    with pytest.raises(errors.DeclarationError) as info:
        load_config(f)
    assert info.value.code == "TM-D003"


def test_profiles_and_exemptions_are_read_from_config(tmp_path):
    f = tmp_path / "pyproject.toml"
    f.write_text(
        '[tool.texmodel]\nprefix = "a"\n[tool.texmodel.exempt]\n"*.pdf" = "why"\n'
        '[tool.texmodel.profiles.print]\nchecks = ["proof-pdf"]\n'
        "[tool.texmodel.profiles.print.options.proof-pdf]\nsafe_mm = 3\n"
    )
    config = load_config(f)
    assert config.exempt == {"*.pdf": "why"}
    assert config.profiles["print"].checks == ("proof-pdf",)
    assert config.profiles["print"].options == {"proof-pdf": {"safe_mm": 3}}
