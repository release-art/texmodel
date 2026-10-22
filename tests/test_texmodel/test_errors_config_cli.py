import logging

import pytest
from typer.testing import CliRunner

from texmodel import cli, errors
from texmodel.config import Config, load_config

runner = CliRunner()


def test_every_error_is_a_texmodel_error_with_code_path_hint():
    for name in ("DeclarationError", "ValidationError", "MigrationError"):
        exc = getattr(errors, name)("boom", code="TM-X1", path="a[0]", hint="fix")
        assert isinstance(exc, errors.TexmodelError)
        assert (exc.code, exc.path, exc.hint) == ("TM-X1", "a[0]", "fix")


def test_load_config(tmp_path):
    f = tmp_path / "pyproject.toml"
    f.write_text("[tool.texmodel]\n")
    assert load_config(f) == Config()


@pytest.mark.parametrize(
    ("body", "code"),
    [("", "TM-D001"), ("[tool.texmodel]\nbogus = 1\n", "TM-D002")],
)
def test_load_config_refuses(tmp_path, body, code):
    f = tmp_path / "pyproject.toml"
    f.write_text(body)
    with pytest.raises(errors.DeclarationError) as info:
        load_config(f)
    assert info.value.code == code


def test_version():
    result = runner.invoke(cli.app, ["version"])
    assert result.exit_code == 0 and result.stdout.strip()


def test_verbose_sets_the_library_logger_and_writes_to_stderr(monkeypatch):
    log = logging.getLogger("texmodel")
    monkeypatch.setattr(log, "handlers", list(log.handlers))
    monkeypatch.setattr(log, "level", log.level)
    assert runner.invoke(cli.app, ["-vv", "version"]).exit_code == 0
    assert log.level == logging.DEBUG
    assert runner.invoke(cli.app, ["-v", "version"]).exit_code == 0
    assert log.level == logging.INFO
