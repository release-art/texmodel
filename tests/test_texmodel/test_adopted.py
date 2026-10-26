"""Adopted packages (M9) and the document preamble (D3): declared-only components, the interface check, `check`."""

import pathlib
from typing import Any

import pytest
from typer.testing import CliRunner

from texmodel import cli
from texmodel._internal.scan import scan_declarations
from texmodel.components import Command, Environment, Value, describe
from texmodel.config import load_config
from texmodel.document import Document
from texmodel.package import Package
from texmodel.preamble import PreambleSlots
from texmodel.types import Length, Raw, Text

from .test_document import codes, refused

runner = CliRunner()

STY = r"""
\ProvidesPackage{hand}
%% \newcommand{\hdCommented}[9]{}
\newcommand{\hdName}[1]{#1}
\newcommand{ \hdSlot }[2][]{#2}
\providecommand\hdBare[1]{#1}
\newcommand{\hdNote}[2][default]{#2}
\newenvironment{hdCard}{}{}
\newenvironment{hdBox}[1]{}{}
\newcommand{\hdPlain}{x}
\renewcommand{\hdPlain}[3]{x}
\newcommand{\other}[1]{}
\string\providecommand\string\hd@x[3]{}
"""


def hand() -> tuple[Package, Any, Any, Any]:
    pkg = Package("hand", prefix="hd", adopted=True)

    @pkg.command
    class Name(Command):
        """The name."""

        text: Text

    @pkg.command
    class Slot(Command):
        """A labelled slot."""

        text: Text
        label: Text | None = None

    @pkg.environment
    class Card(Environment):
        """A card."""

        children = [Name, Slot.times(3)]

    return pkg, Name, Slot, Card


def test_the_scanner_reads_the_declaration_forms_and_nothing_else():
    assert scan_declarations(STY, "hd") == {
        "hdName": "[1]",
        "hdSlot": "[2][]",
        "hdBare": "[1]",
        "hdNote": "[2][]",
        "hdCard": "",
        "hdBox": "[1]",
        "hdPlain": "",
    }


def test_an_adopted_package_renders_no_sty():
    pkg, *_ = hand()
    assert pkg.files() == {}
    with refused("TM-P006"):
        pkg.render()


def test_a_document_of_declared_components_escapes_and_checks_the_grammar():
    pkg, name, slot, card = hand()
    body = card(name(text="R&D"), slot(text="50% of #1", label="Where"))
    assert body.render() == "\\begin{hdCard}\n\\hdName{R\\&D}\n\\hdSlot[Where]{50\\% of \\#1}\n\\end{hdCard}"
    assert "\\usepackage{hand}" in pkg.document(body)
    with pytest.raises(ExceptionGroup) as group:
        pkg.document(card(slot(text="x")))
    assert codes(group) == ["TM-C002"]


def test_a_body_or_a_value_on_an_adopted_package_is_refused():
    pkg = Package("hand", prefix="hd", adopted=True)
    with refused("TM-M032"):

        @pkg.command
        class Bodied(Command):
            """Has a body."""

            body = "x"

    with refused("TM-M032"):

        @pkg.environment
        class Boxed(Environment):
            """Has bodies."""

            begin = "x"
            end = "y"

    with refused("TM-P005"):

        @pkg.value
        class Gap(Value[Length]):
            """A gap."""

            default = Length("1mm")


def test_the_interface_check_finds_missing_names_and_signature_drift():
    assert hand()[0].check_interface(STY) == []
    old = STY.replace(r"\newcommand{ \hdSlot }[2][]{#2}", r"\newcommand{\hdSlot}[1]{#1}").replace(
        r"\newenvironment{hdCard}{}{}", ""
    )
    found = {(v.code, v.path): v for v in hand()[0].check_interface(old)}
    assert set(found) == {("TM-C011", "Slot"), ("TM-C010", "Card")}
    assert "declared [2][], the sources define [1]" in found["TM-C011", "Slot"].message
    assert "declared without arguments" not in found["TM-C011", "Slot"].message


def test_a_declaration_with_no_arguments_is_compared_too():
    pkg = Package("hand", prefix="hd", adopted=True)

    @pkg.command
    class Plain(Command):
        """No arguments."""

    assert pkg.check_interface(r"\newcommand{\hdPlain}{x}") == []
    (v,) = pkg.check_interface(r"\newcommand{\hdPlain}[1]{x}")
    assert "declared without arguments, the sources define [1]" in v.message


def test_the_preamble_goes_around_the_class_and_package_lines():
    pkg, *_ = hand()
    tex = pkg.document(
        Document(
            preamble=PreambleSlots(
                before_class=(Raw(r"\DocumentMetadata{lang=en}"),),
                before_package=(Raw(r"\def\input@path{{res/}}"),),
                after_package=(Raw(r"\graphicspath{{}{res/}}"),),
            )
        )
    )
    assert tex.splitlines()[1:] == [
        r"\DocumentMetadata{lang=en}",
        r"\documentclass{article}",
        r"\def\input@path{{res/}}",
        r"\usepackage{hand}",
        r"\graphicspath{{}{res/}}",
        r"\begin{document}",
        r"\end{document}",
    ]


def test_a_preamble_that_calls_an_undeclared_name_is_refused_with_its_path():
    pkg, *_ = hand()
    with pytest.raises(ExceptionGroup) as group:
        pkg.document(
            Document(preamble=PreambleSlots(after_package=(Raw(r"\setlength{\hdSafeInset}{1mm}"), Raw(r"\hdName{x}"))))
        )
    assert codes(group) == ["TM-M015"]
    (error,) = group.value.exceptions
    assert getattr(error, "path") == "preamble.after_package[0]"  # noqa: B009
    assert r"\hdSafeInset" in str(error)


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[tool.texmodel]\npackage = "adopted_hand:pkg"\nsources = ["res/*.sty"]\n')
    (tmp_path / "adopted_hand.py").write_text(
        "from texmodel.components import Command\nfrom texmodel.package import Package\n"
        "from texmodel.types import Text\n"
        "pkg = Package('hand', prefix='hd', adopted=True)\n\n@pkg.command\nclass Name(Command):\n"
        '    """The name."""\n    text: Text\n'
    )
    (tmp_path / "res").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delitem(__import__("sys").modules, "adopted_hand", raising=False)
    return tmp_path


def test_check_compares_an_adopted_package_with_its_sources(project: pathlib.Path):
    (project / "res" / "hand.sty").write_text(r"\newcommand{\hdName}[1]{#1}")
    ok = runner.invoke(cli.app, ["check"])
    assert ok.exit_code == 0 and "ok: 1 source file(s) define what hand declares" in ok.stdout
    (project / "res" / "hand.sty").write_text(r"\newcommand{\hdName}[2]{#1}")
    drift = runner.invoke(cli.app, ["check"])
    assert drift.exit_code == 1 and "TM-C011 Name: " in drift.stdout


def test_check_without_sources_says_what_to_set(project: pathlib.Path):
    result = runner.invoke(cli.app, ["check"])
    assert result.exit_code == 2 and "TM-D030" in result.stderr and "sources" in result.stderr


def test_the_config_reads_sources(project: pathlib.Path):
    assert load_config(project / "pyproject.toml").sources == ["res/*.sty"]


def test_describe_gives_an_adopted_component_no_body():
    pkg, name, *_ = hand()
    assert describe(name).body is None
