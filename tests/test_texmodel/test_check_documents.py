"""`texmodel check` for documents: each committed file against what the model renders now, by path."""

import sys

import pytest
from typer.testing import CliRunner

from texmodel import cli

runner = CliRunner()

MODULE = """
from texmodel.components import Command, Environment
from texmodel.package import Package
from texmodel.types import Text

pkg = Package("docs-demo", prefix="dd", adopted=True)

@pkg.command
class Item(Command):
    '''An item.'''
    text: Text

@pkg.environment
class Box(Environment):
    '''A box.'''
    children = [Item.times.any()]

def plan():
    return pkg.plan(Box(Item("a"), Item("b")))

def text():
    return pkg.document(Item("a"))
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "docmod.py").write_text(MODULE)
    (tmp_path / "res").mkdir()
    (tmp_path / "res" / "d.sty").write_text(
        r"\newcommand{\ddItem}[1]{#1}" + "\n" + r"\newenvironment{ddBox}{}{}" + "\n"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[tool.texmodel]\npackage = "docmod:pkg"\nsources = ["res/*.sty"]\n'
        '[tool.texmodel.documents]\n"deck.tex" = "docmod:plan()"\n"one.tex" = "docmod:text()"\n'
    )
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    sys.modules.pop("docmod", None)


def render_both():
    assert runner.invoke(cli.app, ["render", "docmod:plan()", "-o", "deck.tex"]).exit_code == 0
    assert runner.invoke(cli.app, ["render", "docmod:text()", "-o", "one.tex"]).exit_code == 0


def test_documents_that_match_the_model_pass(project):
    render_both()
    result = runner.invoke(cli.app, ["check"])
    assert result.exit_code == 0 and "ok: 2 document(s) match the model" in result.stdout


def test_a_hand_edit_is_named_by_the_component_that_writes_the_line(project):
    render_both()
    deck = project / "deck.tex"
    deck.write_text(deck.read_text().replace(r"\ddItem{b}", r"\ddItem{B}"))
    result = runner.invoke(cli.app, ["check"])
    assert result.exit_code == 1
    assert r"changed  deck.tex Box[0]/Item[1]: \ddItem{B}" in result.stdout and "texmodel render" in result.stderr


def test_removed_and_added_lines_are_named_too(project):
    render_both()
    deck = project / "deck.tex"
    deck.write_text(deck.read_text().replace(r"\ddItem{a}" + "\n", "").replace(r"\end{document}", "x\n\\end{document}"))
    out = runner.invoke(cli.app, ["check"]).stdout
    assert r"removed  deck.tex Box[0]/Item[0]: \ddItem{a}" in out and "added    deck.tex Box[0]: x" in out


def test_a_missing_document_and_a_stale_str_document_fail(project):
    render_both()
    (project / "deck.tex").unlink()
    (project / "one.tex").write_text("old")
    out = runner.invoke(cli.app, ["check"]).stdout
    assert "missing  deck.tex" in out and "stale    one.tex" in out


def test_render_writes_the_text_of_a_plan(project):
    render_both()
    assert (project / "deck.tex").read_text() == __import__("docmod").plan().text


def test_render_without_a_pointer_writes_every_configured_document(project):
    result = runner.invoke(cli.app, ["render"])
    assert result.exit_code == 0 and "wrote " in result.stdout
    assert (project / "deck.tex").read_text() == __import__("docmod").plan().text
    assert (project / "one.tex").read_text() == __import__("docmod").text()
    assert runner.invoke(cli.app, ["check"]).exit_code == 0


def test_render_without_a_pointer_needs_documents_and_refuses_output(project):
    refused = runner.invoke(cli.app, ["render", "-o", "x.tex"])
    assert refused.exit_code == 2 and "TM-D031" in refused.stderr
    (project / "pyproject.toml").write_text("[tool.texmodel]\n")
    assert "TM-D031" in runner.invoke(cli.app, ["render"]).stderr


def test_a_plan_pointer_must_name_a_plan(project):
    from texmodel.errors import DeclarationError
    from texmodel.pointer import load_plan

    assert load_plan("docmod:plan()", project).lines
    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-D025"):
        load_plan("docmod:text()", project)
