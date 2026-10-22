"""A library is a part that declares what it defines (§21a 12): the declarations are checked against its TeX."""

import pytest
from typer.testing import CliRunner

from texmodel import cli
from texmodel.body import Syntax
from texmodel.components import Command
from texmodel.errors import DeclarationError
from texmodel.package import Package
from texmodel.types import Text


def fact(p: Package, lib):
    class Fact(Command):
        """A fact."""

        defined_by = lib
        text: Text

    return p.command(Fact)


def test_a_library_that_matches_its_declarations_is_clean():
    p = Package("p", prefix="ac")
    fact(p, p.library("hand", r"\newcommand{\acFact}[1]{#1}" + "\n" + r"\newcommand{\ac@helper}{x}"))
    assert p.check_parts() == []


def test_a_signature_a_missing_name_and_an_undeclared_public_name_are_reported():
    p = Package("p", prefix="ac")
    fact(p, p.library("hand", r"\newcommand{\acFact}[2]{#1#2}" + "\n" + r"\newcommand{\acStray}{x}"))
    other = Package("q", prefix="ac")
    fact(other, other.library("empty", r"\newcommand{\acOther}{x}"))
    assert [(v.code, v.path) for v in p.check_parts()] == [("TM-C011", "Fact"), ("TM-C012", "hand")]
    assert [(v.code, v.path) for v in other.check_parts()] == [("TM-C010", "Fact"), ("TM-C012", "empty")]


def test_a_name_defined_twice_is_reported_and_refuses_generation():
    p = Package("p", prefix="ac")
    p.library("one", r"\newcommand{\ac@x}{1}")
    p.library("two", r"\newcommand{\ac@x}{2}")
    p.library("three", r"\newcommand{\ac@x}{3}")
    assert [v.message for v in p.check_parts()] == [
        "\\ac@x is defined by library one and by library two",
        "\\ac@x is defined by library one and by library three",
    ]
    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-P012"):
        p.render()


def test_a_library_and_a_rendered_component_may_not_define_one_name():
    p = Package("p", prefix="ac")
    p.library("hand", r"\newcommand{\acFact}[1]{#1}")

    @p.command
    class Fact(Command):
        """A fact."""

        text: Text

        def body(self):
            return r"#text"

    assert [(v.code, v.message) for v in p.check_parts()] == [
        ("TM-C013", "\\acFact is defined by Fact and by library hand")
    ]


def test_an_expl3_library_is_not_read():
    p = Package("p", prefix="ac")
    fact(p, p.library("hand", r"\cs_new:Npn \acFact:n #1 {#1}", syntax=Syntax.EXPL3))
    assert p.check_parts() == []


def test_check_reports_the_violations_of_a_generated_package(tmp_path, monkeypatch):
    (tmp_path / "mod.py").write_text(
        "from texmodel.components import Command\nfrom texmodel.package import Package\n"
        "from texmodel.types import Text\n"
        "pkg = Package('p', prefix='ac')\nlib = pkg.library('hand', r'\\newcommand{\\acFact}[2]{#1#2}')\n"
        "@pkg.command\nclass Fact(Command):\n    '''A fact.'''\n    defined_by = lib\n    text: Text\n"
    )
    (tmp_path / "pyproject.toml").write_text('[tool.texmodel]\npackage = "mod:pkg"\noutput = "gen"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    runner = CliRunner()
    runner.invoke(cli.app, ["build"])
    result = runner.invoke(cli.app, ["check"])
    assert result.exit_code == 1 and "TM-C011 Fact" in result.stdout
