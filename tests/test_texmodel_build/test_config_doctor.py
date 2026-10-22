import json
import logging
import shutil

import pytest
from typer.testing import CliRunner

from texmodel.errors import DeclarationError
from texmodel_build import cli
from texmodel_build.config import BuildConfig, Target, load_build_config

runner = CliRunner()


def test_build_config_defaults_and_targets(tmp_path):
    f = tmp_path / "pyproject.toml"
    f.write_text(
        '[tool.texmodel-build]\nimage = "img:1"\n[tool.texmodel-build.targets.card]\nsource = "card.tex"\n'
        '[tool.texmodel-build.targets.deck]\nsource = "deck.tex"\nvariant = "print"\nprofile = "pdfx4"\n'
    )
    config = load_build_config(f)
    assert config.image == "img:1" and config.engine == "lualatex" and set(config.targets) == {"card", "deck"}
    assert config.targets["deck"] == Target(name="deck", source="deck.tex", variant="print", profile="pdfx4")
    f.write_text("[tool.texmodel-build]\n")
    assert load_build_config(f) == BuildConfig()


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("", "TM-D001"),
        ("[tool.texmodel-build]\nbogus = 1\n", "TM-D002"),
        ("[tool.texmodel-build.targets.x]\nbogus = 1\n", "TM-D003"),
    ],
)
def test_build_config_refuses(tmp_path, body, code):
    f = tmp_path / "pyproject.toml"
    f.write_text(body)
    with pytest.raises(DeclarationError) as info:
        load_build_config(f)
    assert info.value.code == code


def test_profiles_and_exemptions_are_read_from_config(tmp_path):
    f = tmp_path / "pyproject.toml"
    f.write_text(
        '[tool.texmodel-build.exempt]\n"*.pdf" = "why"\n'
        '[tool.texmodel-build.profiles.print]\nchecks = ["proof-pdf"]\n'
        "[tool.texmodel-build.profiles.print.options.proof-pdf]\nsafe_mm = 3\n"
    )
    config = load_build_config(f)
    assert config.exempt == {"*.pdf": "why"}
    assert config.profiles["print"].checks == ("proof-pdf",)
    assert config.profiles["print"].options == {"proof-pdf": {"safe_mm": 3}}


def test_doctor_exit_3_when_required_tool_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    result = runner.invoke(cli.app, ["doctor", "--json"])
    assert result.exit_code == 3
    assert {t["name"] for t in json.loads(result.output)["tools"]} == set(cli.TOOLS)


def test_doctor_ok_when_tools_present(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shutil, "which", lambda name: f"/bin/{name}")
    assert runner.invoke(cli.app, ["doctor"]).exit_code == 0
    assert runner.invoke(cli.app, ["version"]).exit_code == 0


def test_verbose_logs_to_stderr_not_stdout(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    log = logging.getLogger("texmodel_build")
    monkeypatch.setattr(log, "handlers", list(log.handlers))
    monkeypatch.setattr(log, "level", log.level)
    monkeypatch.setattr(logging.getLogger("texmodel"), "handlers", [])
    monkeypatch.setattr(shutil, "which", lambda name: f"/bin/{name}")
    result = runner.invoke(cli.app, ["-vv", "doctor", "--json"])
    assert "DEBUG texmodel_build.cli: probe lualatex -> /bin/lualatex" in result.stderr
    assert json.loads(result.stdout)  # stdout is still clean JSON
    assert log.level == logging.DEBUG
    assert runner.invoke(cli.app, ["-v", "version"]).exit_code == 0
    assert log.level == logging.INFO


def test_measures_are_read_from_config_and_a_bad_one_is_refused(tmp_path):
    f = tmp_path / "pyproject.toml"
    rule = r'package = "pk"\npattern = "(?P<item>a) (?P<needs>b) (?P<has>c)"\n'
    f.write_text("[tool.texmodel-build.measures.fit]\n" + rule.replace("\\n", "\n"))
    (measure,) = load_build_config(f).measures.values()
    assert (measure.name, measure.package, measure.kind.value) == ("fit", "pk", "fit")
    f.write_text('[tool.texmodel-build.measures.fit]\npackage = "pk"\npattern = "("\n')
    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-D032"):
        load_build_config(f)
