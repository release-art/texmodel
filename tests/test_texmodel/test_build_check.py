import shutil

import pytest
from typer.testing import CliRunner

from texmodel import cli
from texmodel.drift import stamp
from texmodel.errors import DeclarationError
from texmodel.package import Package, generator_version

from .conftest import FIXTURES

runner = CliRunner()


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project that declares the fixture package, with its sources copied beside the pyproject."""
    shutil.copytree(
        FIXTURES / "acme_cards", tmp_path / "acme_cards", ignore=shutil.ignore_patterns("generated", "__pycache__")
    )
    (tmp_path / "pyproject.toml").write_text('[tool.texmodel]\npackage = "acme_cards:pkg"\noutput = "gen"\n')
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
    (project / "pyproject.toml").write_text(f'[tool.texmodel]\npackage = "{package}"\n')
    for command in ("build", "check"):
        result = runner.invoke(cli.app, [command])
        assert result.exit_code == 2 and code in result.stderr


def _module(project, text):
    (project / "mydocs.py").write_text("from acme_cards import *\nfrom texmodel.document import Document\n" + text)


@pytest.fixture
def docs(project):
    yield project
    import sys

    sys.modules.pop("mydocs", None)


def test_render_writes_a_document_from_a_str_or_a_function(docs):
    _module(
        docs,
        "card = pkg.document(CardBack(Name(text='Rex'), Fact(text='50% of $5'), Fact(text='b')))\n"
        "def other():\n    return pkg.document(Fact(text='x'))\n",
    )
    first = runner.invoke(cli.app, ["render", "mydocs:card"])
    assert first.exit_code == 0 and first.stdout.strip() == "wrote card.tex"
    assert "\\acFact{50\\% of \\$5}" in (docs / "card.tex").read_text()
    second = runner.invoke(cli.app, ["render", "mydocs:other", "-o", "out/deep/o.tex"])
    assert second.exit_code == 0 and "\\acFact{x}" in (docs / "out" / "deep" / "o.tex").read_text()


def test_render_reports_every_violation_and_writes_nothing(docs):
    _module(docs, "def bad():\n    return pkg.document(Document(CardBack(), Name(text=1), options=['a]b']))\n")
    result = runner.invoke(cli.app, ["render", "mydocs:bad"])
    assert result.exit_code == 2 and not (docs / "bad.tex").exists()
    err = result.stderr
    assert err.count("error TM-") == 4 and "TM-C002 at CardBack" in err and "TM-C006" in err and "hint:" in err


def test_render_refuses_what_is_not_a_document(docs):
    _module(docs, "number = 3\ndef boom():\n    raise ExceptionGroup('x', [ValueError('not ours')])\n")
    for spec, code in (("mydocs:number", "TM-D024"), ("mydocs:missing", "TM-D021"), ("nocolon", "TM-D020")):
        result = runner.invoke(cli.app, ["render", spec])
        assert result.exit_code == 2 and code in result.stderr
    assert runner.invoke(cli.app, ["render", "mydocs:boom"]).exit_code != 0  # a foreign error group is not swallowed


@pytest.fixture
def pointers(project):
    (project / "deckmod.py").write_text(
        "from acme_cards import pkg as _pkg\n"
        "class Decks:\n    main = _pkg\n    @staticmethod\n    def make():\n        return _pkg\n"
        "def get_pkg():\n    return _pkg\n"
        "def needs_argument(x):\n    return _pkg\n"
    )
    yield project
    import sys

    sys.modules.pop("deckmod", None)


@pytest.mark.parametrize("pointer", ["deckmod:Decks.main", "deckmod:get_pkg()", "deckmod:Decks.make()"])
def test_a_package_pointer_may_name_a_nested_object_or_a_getter_to_call(pointers, pointer):
    (pointers / "pyproject.toml").write_text(f'[tool.texmodel]\npackage = "{pointer}"\noutput = "gen"\n')
    assert runner.invoke(cli.app, ["build"]).exit_code == 0
    assert (pointers / "gen" / "acme-cards.sty").is_file()


@pytest.mark.parametrize(
    ("pointer", "code"),
    [("deckmod:needs_argument()", "TM-D021"), ("deckmod:Decks.nope", "TM-D021"), ("deckmod:Decks.main()", "TM-D021"),
     ("deckmod:", "TM-D020"), (":x", "TM-D020"), ("deck mod:x", "TM-D020"), ("deckmod:get_pkg(1)", "TM-D020"),
     ("deckmod:a..b", "TM-D020")],
)  # fmt: skip
def test_a_bad_pointer_exits_2_with_a_code(pointers, pointer, code):
    (pointers / "pyproject.toml").write_text(f'[tool.texmodel]\npackage = "{pointer}"\n')
    result = runner.invoke(cli.app, ["build"])
    assert result.exit_code == 2 and code in result.stderr


def test_render_names_the_file_after_the_last_part_of_the_pointer(pointers):
    (pointers / "pyproject.toml").write_text("[tool.texmodel]\n")
    (pointers / "deckmod.py").write_text(
        (pointers / "deckmod.py").read_text()
        + "class Docs:\n    @staticmethod\n    def card():\n        return _pkg.document()\n"
    )
    result = runner.invoke(cli.app, ["render", "deckmod:Docs.card()"])
    assert result.exit_code == 0 and (pointers / "card.tex").is_file()


def test_check_names_the_component_of_a_hand_edited_line_in_the_sty(project):
    runner.invoke(cli.app, ["build"])
    sty = project / "gen" / "acme-cards.sty"
    sty.write_text(sty.read_text().replace(r"\newcommand{\acFact}[1]{%", r"\newcommand{\acFact}[1]{% x", 1))
    out = runner.invoke(cli.app, ["check"]).stdout
    assert (
        r"changed  gen/acme-cards.sty Fact: \newcommand{\acFact}[1]{% x" in out and "stale    gen/acme-cards.sty" in out
    )
    sty.write_text(sty.read_text().replace("\n\n", "\n", 1))  # the blank line before the first item is gone too
    assert "removed  gen/acme-cards.sty requires: " in runner.invoke(cli.app, ["check"]).stdout  # a blank line


def test_the_sty_plan_has_a_path_per_component_and_its_text_is_the_sty(project, monkeypatch):
    monkeypatch.syspath_prepend(str(project))
    from acme_cards import pkg  # pyright: ignore[reportMissingImports]

    plan = pkg.render_plan()
    assert plan.text == pkg.render() and plan.path_of(1).startswith("header") and plan.lines[3].path == "requires"
    assert {x.path for x in plan.lines} >= {"header", "requires", "Fact", "CardBack"}
    assert plan.edits(plan.text) == []
    empty = Package("empty-demo", prefix="em")
    assert (
        empty.render()
        == "".join([f"% empty-demo.sty -- {stamp(generator_version())}. Do not edit; run `texmodel build`.\n"])
        + "\\NeedsTeXFormat{LaTeX2e}\n\\ProvidesPackage{empty-demo}\n% v0.0.0 empty-demo\n\n\n"
    )


FAMILY = '''
from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Text

core = Package("fam-core", prefix="fc")
birds = Package("fam-birds", prefix="fb")
birds.require(core)

@core.command
class Fact(Command):
    """A fact."""
    text: Text
    def body(self):
        return r"#text"

@birds.command
class Bird(Command):
    """A bird."""
    text: Text
    def body(self):
        return r"#text"

def family():
    return [core, birds]
'''


@pytest.fixture
def family(tmp_path, monkeypatch):
    (tmp_path / "fam.py").write_text(FAMILY)
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    import sys

    sys.modules.pop("fam", None)


@pytest.mark.parametrize("pointer", ['["fam:core", "fam:birds"]', '"fam:family()"', '["fam:family()", "fam:core"]'])
def test_a_family_of_packages_builds_and_checks_together(family, pointer):
    (family / "pyproject.toml").write_text(f'[tool.texmodel]\npackage = {pointer}\noutput = "gen"\n')
    built = runner.invoke(cli.app, ["build"])
    assert (
        built.exit_code == 0 and "wrote gen/fam-core.sty" in built.stdout and "wrote gen/fam-birds.sty" in built.stdout
    )
    assert runner.invoke(cli.app, ["check"]).stdout.strip() == "ok: generated files are current"
    (family / "gen" / "fam-birds.sty").write_text("% hand edit\n")
    stale = runner.invoke(cli.app, ["check"])
    assert (
        stale.exit_code == 1 and "stale    gen/fam-birds.sty" in stale.stdout and "gen/fam-core.sty" not in stale.stdout
    )


def test_a_family_is_refused_when_it_cannot_be_told_apart_or_is_not_packages(family):
    def run(pointer, *args):
        (family / "pyproject.toml").write_text(f'[tool.texmodel]\npackage = {pointer}\nschema_output = "s.json"\n')
        return runner.invoke(cli.app, list(args or ["build"]))

    assert "TM-D022" in run('["fam:core", "fam:Fact"]').stderr  # Fact is not a Package
    assert "TM-D022" in run('"fam:family"').stderr  # a function, not an iterable of Packages
    assert "TM-D034" in run('["fam:core", "fam:birds"]', "schema").stderr
    assert run('"fam:core"', "schema").exit_code == 0


def test_a_pointer_names_one_package_or_a_family_of_distinct_names(family):
    from texmodel.pointer import load_packages

    (core,) = load_packages("fam:core", family)
    assert (
        load_packages("fam:core", family) == (core,) and len(load_packages(["fam:family()", "fam:core"], family)) == 2
    )
    (family / "other.py").write_text('from texmodel.package import Package\ncore = Package("fam-core", prefix="x")\n')
    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-D026"):
        load_packages(["fam:core", "other:core"], family)
    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-D022"):
        load_packages("fam:Fact", family)


def test_the_header_may_have_no_date_and_carry_a_text_of_its_own():
    head = (
        Package("hd-demo", prefix="hd", date=None, header="Property of the studio.\nDo not forward.")
        .render()
        .splitlines()
    )
    assert head[0].startswith("% hd-demo.sty -- generated with texmodel")
    assert head[1:6] == [
        "% Property of the studio.",
        "% Do not forward.",
        "\\NeedsTeXFormat{LaTeX2e}",
        "\\ProvidesPackage{hd-demo}",  # LaTeX reads the first word of a bracket as a date
        "% v0.0.0 hd-demo",
    ]
    dated = Package("hd-demo", prefix="hd", date="2026/10/22", version="1.0.0").render().splitlines()
    assert dated[2] == "\\ProvidesPackage{hd-demo}[2026/10/22 v1.0.0 hd-demo]"
    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-P003"):
        Package("hd-demo", prefix="hd", date="soon")
