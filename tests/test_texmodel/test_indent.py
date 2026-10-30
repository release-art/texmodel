"""A document's body is indented two spaces per level of environment (G1)."""

import re

import pytest
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.body import Comment
from texmodel.components import Command, Environment, Passthrough
from texmodel.document import Document
from texmodel.package import Package
from texmodel.testing import Call, expand
from texmodel.types import Raw, Text

from .test_stubs import calls, probed

pkg = Package("indent-demo", prefix="id")


@pkg.command
class Item(Command):
    """An item."""

    text: Text
    body = r"\par #text\par"


@pkg.command
class Block(Command):
    """Raw TeX over several lines."""

    tex: Raw
    body = r"#tex"


@pkg.environment
class Inner(Environment):
    """The inner box."""

    children = [Item.times.any(), Block.times.any(), Passthrough.times.any()]
    begin = r"\begin{center}"
    end = r"\end{center}"


@pkg.environment
class Outer(Environment):
    """The outer box."""

    children = [Inner.times.any(), Item.times.any()]
    begin = r"\begin{quote}"
    end = r"\end{quote}"


TREE = Outer(Inner(Item(text="a"), Comment("note"), Item(text="b")), Item(text="c"))


def test_each_level_takes_two_spaces_and_render_agrees_with_the_plan():
    assert TREE.render().splitlines() == [
        r"\begin{idOuter}",
        r"  \begin{idInner}",
        r"    \idItem{a}",
        r"    % note",
        r"    \idItem{b}",
        r"  \end{idInner}",
        r"  \idItem{c}",
        r"\end{idOuter}",
    ]
    assert pkg.plan(TREE).text.splitlines()[-9:-1] == TREE.render().splitlines()


def test_a_passthrough_and_the_continuation_lines_of_a_call_are_verbatim():
    verbatim = "\\begin{verbatim}\n  two spaces\n\\end{verbatim}"
    tree = Outer(Inner(Block(tex=Raw("a\n\n  b")), Passthrough(Raw(verbatim))))
    assert tree.render().splitlines() == [
        r"\begin{idOuter}",
        r"  \begin{idInner}",
        r"    \idBlock{a",
        "",
        "  b}",
        *verbatim.splitlines(),
        r"  \end{idInner}",
        r"\end{idOuter}",
    ]


def test_a_comment_is_indented_on_each_of_its_lines():
    assert Outer(Inner(Comment("a\n\nb"))).render().splitlines()[2:5] == ["    % a", "    %", "    % b"]


def test_spans_follow_the_prefix_so_a_hand_edit_still_names_the_field():
    plan = pkg.plan(TREE)
    line = next(x for x in plan.lines if x.path == "Outer[0]/Inner[0]/Item[0]")
    assert [(s.arg, line.tex[s.start : s.end]) for s in line.spans] == [("text", "a")]
    (edit,) = plan.edits(plan.text.replace("{a}", "{A}"))
    assert edit.path == "Outer[0]/Inner[0]/Item[0]" and [f.arg for f in edit.fields] == ["text"]


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_tex_reads_the_indented_document_as_the_flat_one(compiler):  # noqa: F811
    stubs = [Item, Inner, Outer]
    indented = pkg.test_document(Document(TREE), stub=stubs)
    flat = re.sub(r"(?m)^ +", "", indented)
    assert indented != flat
    files = {"indent-demo.sty": pkg.render()}
    got = await probed(compiler, indented, files)
    assert got == await probed(compiler, flat, files) == calls(expand(TREE, stubs))
    assert isinstance(got[0], Call)
