"""Stubbed unit tests (§21): the fast tier, and the TeX tier agreeing with it."""

import importlib
import pathlib
import re

import pytest
from card_deck import convert, model
from hypothesis import (
    given,
    strategies as st,
)
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.body import Comment, Cs, Group, Hole, Lit, RefKind, Seq
from texmodel.components import Command, Environment, Passthrough
from texmodel.document import Document
from texmodel.package import Package
from texmodel.run.errors import CompileError
from texmodel.run.testkit import run_probes
from texmodel.testing import Call, detokenized, expand, stub_tex
from texmodel.types import Raw, Text

from .test_document import refused

EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"


@pytest.fixture
def composed(monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLES))
    return importlib.import_module("composed")


def calls(items):
    return [c for c in items if isinstance(c, Call)]


# --- the fast tier -----------------------------------------------------------------------------------------------


def test_detokenized_is_what_detokenize_shows():
    assert detokenized("  R\\&D 50\\%") == "R\\&D 50\\%"
    assert detokenized("\\textbf{x}  and\n\ty") == "\\textbf {x} and y"
    assert detokenized("\\a   \\b x") == "\\a \\b x"  # spaces after a control word are skipped
    assert detokenized("\\ \\  x") == "\\ \\ x"
    assert detokenized("a\\") == "a\\"


@given(st.text(alphabet="ab \\{}&%\n", max_size=12))
def test_detokenized_is_stable(text):
    assert detokenized(detokenized(text)) == detokenized(text)


@given(
    st.text(alphabet=st.characters(blacklist_characters="\\{}"), max_size=6),
    st.lists(st.sampled_from(["a", "b c", r"\{x\}", "{n}", r"\\"]), max_size=3),
)
def test_a_probe_value_parses_back(name, args):
    name = "k" + name.replace(":", "")
    for kind in RefKind:
        call = Call(name, () if kind is RefKind.CLOSE else tuple(args), kind)
        assert Call.parse(call.probe_value()) == call


def test_expand_returns_text_and_the_calls_of_stubs_in_order(composed):
    base, pkg = composed.base, composed.pkg
    section = composed.Section(composed.Entry(text="First"), composed.Entry(text="R&D 50%"), title="Notes")
    assert calls(expand(section, [composed.Fact])) == [
        Call("bkFact", ("First",)),
        Call("bkFact", (r"R\&D 50\%",)),
    ]
    both = expand(section, [composed.Fact, composed.Panel])
    assert [(c.kind, c.name, c.args) for c in calls(both)] == [
        (RefKind.OPEN, "bkPanel", ("Notes",)),
        (RefKind.CALL, "bkFact", ("First",)),
        (RefKind.CALL, "bkFact", (r"R\&D 50\%",)),
        (RefKind.CLOSE, "bkPanel", ()),
    ]
    assert any(isinstance(x, str) and r"\par\hrule" in x for x in both)
    plain = expand(section)
    assert calls(plain) == [] and any(isinstance(x, str) and r"\par\noindent First\par" in x for x in plain)
    assert base is not pkg  # two packages took part


def test_an_unregistered_class_cannot_be_stubbed():
    class Loose(Command):
        """Not in a package."""

        text: Text

    with refused("TM-M019"):
        expand(Loose(text="x"), [Loose])


def test_optional_arguments_comments_passthrough_and_adopted_components():
    pkg = Package("stub-demo", prefix="sd")

    @pkg.command
    class Slot(Command):
        """A slot."""

        body = "#label #text"
        text: Text
        label: Text | None = None

    @pkg.environment
    class Box(Environment):
        """A box."""

        children = [Slot.times.any(), Passthrough.times.any()]
        begin = r"\begin{center}"
        end = r"\end{center}"

    node = Box(Slot(text="a"), Comment("note"), Passthrough(Raw(r"\vspace{1mm}")), Slot(text="b", label="L"))
    out = expand(node, [Slot])
    assert r"\renewenvironment{sdBox}" in stub_tex([Box])
    assert calls(out) == [Call("sdSlot", ("", "a")), Call("sdSlot", ("L", "b"))]
    assert r"\vspace{1mm}" in "".join(x for x in out if isinstance(x, str)) and "note" not in "".join(
        x for x in out if isinstance(x, str)
    )
    adopted = Package("ad", prefix="ad", adopted=True)

    @adopted.command
    class Name(Command):
        """Hand-written."""

        text: Text

    assert expand(Name(text="x")) == [] and calls(expand(Name(text="x"), [Name])) == [Call("adName", ("x",))]


# --- the TeX tier agrees -----------------------------------------------------------------------------------------


async def probed(comp, tex, files):  # noqa: ANN001
    found = await run_probes(comp, tex, files)
    numbered = sorted((int(m.name.removeprefix("call")), m.value) for m in found if re.fullmatch(r"call\d+", m.name))
    return [Call.parse(value) for _, value in numbered]


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_the_tex_tier_gives_the_fast_tiers_calls_across_two_packages(compiler, composed):  # noqa: F811
    section = composed.Section(composed.Entry(text="First"), composed.Entry(text="R&D 50%"), title="Notes")
    stubs = [composed.Fact, composed.Panel]
    tex = composed.pkg.test_document(section, stub=stubs)
    files = {f"{p.name}.sty": p.render() for p in (composed.base, composed.pkg)}
    assert await probed(compiler, tex, files) == calls(expand(section, stubs))
    only_fact = composed.pkg.test_document(section, stub=[composed.Fact])  # the real panel runs, the facts are stubbed
    assert await probed(compiler, only_fact, files) == calls(expand(section, [composed.Fact]))


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_a_stubs_arguments_with_every_special_survive(compiler):  # noqa: F811
    pkg = Package("special-demo", prefix="sp")

    @pkg.command
    class Fact(Command):
        """A fact."""

        body = r"\par #text #note"
        text: Text
        note: Text | None = None

    text = "Call 999 or go to A&E: 30% of #1 _a_ ~b ^c $5 {d} \\e <f> “g” ‘h’ it’s — i  two   spaces"
    nodes = [Fact(text=text), Fact(text="x", note=text)]
    tex = pkg.test_document(*nodes, stub=[Fact])
    expected = [c for n in nodes for c in calls(expand(n, [Fact]))]
    assert await probed(compiler, tex, {"special-demo.sty": pkg.render()}) == expected
    assert (
        "A\\&E" in expected[0].args[1]
        and "\\textasciitilde {}b" in expected[0].args[1]
        and "two spaces" in expected[0].args[1]
    )  # one space, as TeX read it
    assert expected[1].args == (expected[0].args[1], "x")  # the optional note comes first in TeX order


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_the_tex_tier_agrees_on_the_card_deck_consumer(compiler):  # noqa: F811
    project = convert.load()[0]
    card = convert.nodes()[0]
    stubs = [
        model.Card,
        model.CardFront,
        model.CardImage,
        model.CardBack,
        model.Name,
        model.LeadFact,
        model.LabelledSlot,
    ]
    tex = model.pkg.test_document(
        Document(
            model.CardHeader("Red Fox", "1"),
            card,
            settings=convert.settings(project),
            preamble=convert.preamble(project),
        ),
        stub=stubs,
    )
    files = {"res/card-deck.sty": (convert.HERE / "res" / "card-deck.sty").read_text(encoding="utf-8")}
    got = await probed(compiler, tex, files)
    assert got == calls(expand(card, stubs))
    assert got[0] == Call("cdCard", (), RefKind.OPEN) and got[-1] == Call("cdCard", (), RefKind.CLOSE)
    labels = {c.args[0] for c in got if c.name == "cdLabelledSlot"}
    assert labels == {
        "\\deckParamFactSpot ",
        "\\deckParamFactSound ",
        "\\deckParamFactWhere ",
    }  # a Choice, shown by detokenize


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_a_broken_document_raises_instead_of_returning_probes(compiler, tmp_path):  # noqa: F811
    with pytest.raises(CompileError):
        await run_probes(compiler, "\\documentclass{article}\\begin{document}\\nonexistent\\end{document}")


def test_constructive_pieces_comments_and_a_stub_inside_a_group_are_walked():
    pkg = Package("piece-demo", prefix="pc")

    @pkg.command
    class Inner(Command):
        """Called inside a group."""

        text: Text

        body = "#text"

    @pkg.command
    class Outer(Command):
        """Builds its body from pieces."""

        text: Text

        def body(self):
            yield Comment("explains")
            yield Seq(Cs("textbf"), Group(Lit("a & b "), Hole("text"), Raw("!"), Inner.call(Hole("text"))))

    out = expand(Outer(text="x_y"), [Inner])
    assert out == [r"\textbf{a \& b x\_y!", Call("pcInner", (r"x\_y",)), "}\n"]
    assert expand(Outer(text="x_y")) == ["\\textbf{a \\& b x\\_y!x\\_y\n}\n"]  # the callee's body is a line of its own
