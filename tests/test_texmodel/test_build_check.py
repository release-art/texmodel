import shutil

import pytest
from typer.testing import CliRunner

from texmodel import cli

from .conftest import FIXTURES

runner = CliRunner()


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project that declares the fixture package, with its sources copied beside the pyproject."""
    shutil.copytree(
        FIXTURES / "acme_cards", tmp_path / "acme_cards", ignore=shutil.ignore_patterns("generated", "__pycache__")
    )
    (tmp_path / "pyproject.toml").write_text(
        '[tool.texmodel]\nprefix = "ac"\npackage = "acme_cards:pkg"\noutput = "gen"\n'
    )
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    import sys

    for name in [m for m in sys.modules if m == "acme_cards" or m.startswith("acme_cards.")]:
        del sys.modules[name]


def test_build_writes_the_sty_and_check_agrees(project):
    built = runner.invoke(cli.app, ["build"])
    assert built.exit_code == 0 and "wrote gen/acme-cards.sty" in built.stdout
    sty = (project / "gen" / "acme-cards.sty").read_text()
    assert "\\newcommand{\\acFact}[1]{%" in sty and "generated with texmodel" in sty.splitlines()[0]
    assert runner.invoke(cli.app, ["check"]).stdout.strip() == "ok: generated files are current"


def test_check_reports_a_hand_edit_a_deletion_and_an_orphan(project):
    runner.invoke(cli.app, ["build"])
    sty = project / "gen" / "acme-cards.sty"
    sty.write_text(sty.read_text() + "% hand edit\n")
    (project / "gen" / "old.sty").write_text("nobody generates me")
    result = runner.invoke(cli.app, ["check"])
    assert result.exit_code == 1 and "stale    gen/acme-cards.sty" in result.stdout
    assert "orphaned gen/old.sty" in result.stdout and "run `texmodel build`" in result.stderr
    sty.unlink()
    assert "missing  gen/acme-cards.sty" in runner.invoke(cli.app, ["check"]).stdout


def test_check_says_which_texmodel_version_wrote_a_stale_file(project):
    runner.invoke(cli.app, ["build"])
    sty = project / "gen" / "acme-cards.sty"
    sty.write_text(
        sty.read_text()
        .replace("generated with texmodel", "generated with texmodel 0.0.0 --", 1)
        .replace("-- 0", "0", 1)
    )
    result = runner.invoke(cli.app, ["check"])
    assert result.exit_code == 1 and "current is" in result.stdout


@pytest.mark.parametrize(
    ("package", "code"),
    [("", "TM-D023"), ("nocolon", "TM-D020"), ("no_such_module:x", "TM-D021"), ("acme_cards:missing", "TM-D021"),
     ("acme_cards:Fact", "TM-D022")],
)  # fmt: skip
def test_bad_package_declarations_exit_2_with_a_code(project, package, code):
    (project / "pyproject.toml").write_text(f'[tool.texmodel]\nprefix = "ac"\npackage = "{package}"\n')
    for command in ("build", "check"):
        result = runner.invoke(cli.app, [command])
        assert result.exit_code == 2 and code in result.stderr
