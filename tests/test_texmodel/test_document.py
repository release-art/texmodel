"""Escaping (T3), environments (M1a), grammar and validation (M4, D5, E2), documents (D1, D1a, D2)."""

import re
import types

import pytest
from hypothesis import (
    given,
    strategies as st,
)

from texmodel.components import Command, Environment, Repeat, Value
from texmodel.document import Document
from texmodel.errors import DeclarationError, ValidationError
from texmodel.package import Package
from texmodel.types import Colour, Gray, Length, Raw, Text, balanced, escape

_TOKEN = re.compile(r"\\textbackslash\{\}|\\textasciitilde\{\}|\\textasciicircum\{\}|\\[&%$#_{}]")


def refused(code: str):
    return pytest.raises(DeclarationError, check=lambda e: e.code == code)


def codes(group: pytest.ExceptionInfo[ExceptionGroup]) -> list[str]:
    return [getattr(e, "code") for e in group.value.exceptions]  # noqa: B009


def shop():
    """A small package: two commands, a raw command, an environment with a grammar, and one of each value."""
    p = Package("shop", prefix="sh", document_class="article")

    @p.command
    class Name(Command):
        """Title."""

        body = "\\textbf{#text}"

        text: Text

    @p.command
    class Fact(Command):
        """A fact."""

        body = "#text"

        text: Text

    @p.command
    class Slot(Command):
        """Labelled."""

        body = "#label #text"

        text: Text
        label: Text | None = None

    @p.command
    class Tex(Command):
        """Raw TeX in."""

        body = "#tex#note"

        tex: Raw
        note: Raw | None = None

    @p.environment
    class Card(Environment):
        """A card."""

        begin = "\\begin{center}#title"
        end = "\\end{center}"

        children = [Name, Fact.times(2, 3), Slot.times(3)]
        title: Text | None = None

    @p.value
    class Gap(Value[Length]):
        """Gap."""

        default = Length("2mm")

    @p.value
    class Ink(Value[Colour]):
        """Ink."""

        default = Gray(0)

    @p.value
    class Tight(Value[bool]):
        """Tight."""

        default = False

    return types.SimpleNamespace(**dict(locals()))


@given(st.text())
def test_escaped_text_has_no_live_specials_and_stays_balanced(text):
    out = escape(text)
    assert not set(_TOKEN.sub("", out)) & set("\\&%$#_{}~^") and balanced(out)


def test_every_special_has_its_literal():
    assert escape("a & b 50% $5 #1 x_y {z} ~ ^ \\") == (
        r"a \& b 50\% \$5 \#1 x\_y \{z\} \textasciitilde{} \textasciicircum{} \textbackslash{}"
    )
    assert escape(r"\&") == r"\textbackslash{}\&"  # one pass: what escape wrote is never escaped again


def test_raw_must_balance_and_is_not_a_str():
    assert Raw("\\textbf{x}").tex == "\\textbf{x}" and not isinstance(Raw("x"), str)
    for bad in ("{", "}", "}{", "\\textbf{x"):
        with pytest.raises(ValidationError, check=lambda e: e.code == "TM-C007"):
            Raw(bad)
    assert Raw("\\{ % }\n x").tex  # an escaped brace and a comment do not count


def test_text_is_escaped_and_raw_is_not():
    s = shop()
    assert s.Fact("50% of $5").render() == "\\shFact{50\\% of \\$5}"
    assert s.Tex(Raw("\\emph{x}")).render() == "\\shTex{\\emph{x}}"


def test_the_optional_argument_comes_first_is_omitted_when_none_and_wraps_a_bracket():
    s = shop()
    assert s.Slot("t", label="Sound").render() == "\\shSlot[Sound]{t}"
    assert s.Slot("t").render() == "\\shSlot{t}"
    assert s.Slot("t", label="a]b").render() == "\\shSlot[{a]b}]{t}"
    assert s.Tex(Raw("x"), note=Raw("a]b")).render() == "\\shTex[{a]b}]{x}"


def test_a_field_of_the_wrong_kind_is_a_violation_with_its_path():
    s = shop()
    bad = s.Card(s.Name(Raw("x")), s.Fact("a"), s.Fact("b"), s.Tex("plain"))
    found = {(v.code, v.path) for v in bad.violations()}
    assert ("TM-C003", "Card/Name[0].text") in found and ("TM-C003", "Card/Tex[3].tex") in found
    assert s.Slot("x", label=None).violations() == [] and s.Fact(None).violations()[0].code == "TM-C003"  # pyright: ignore[reportArgumentType]


def test_an_unregistered_component_cannot_render():
    class Loose(Command):
        """Not registered."""

        body = "x"

    with refused("TM-M019"):
        Loose().render()


def test_an_environment_renders_its_children_between_begin_and_end():
    s = shop()
    card = s.Card(s.Name("Rex"), s.Fact("a"), s.Fact("b"), title="T")
    assert card.render() == "\\begin{shCard}[T]\n\\shName{Rex}\n\\shFact{a}\n\\shFact{b}\n\\end{shCard}"
    assert repr(card) == "Card(Name('Rex'), Fact('a'), Fact('b'), title='T')"
    assert card == s.Card(s.Name("Rex"), s.Fact("a"), s.Fact("b"), title="T") and hash(card) == hash(
        s.Card(s.Name("Rex"), s.Fact("a"), s.Fact("b"), title="T")
    )
    assert card != s.Card(s.Name("Rex"), s.Fact("a"), s.Fact("b"))
    assert "\\newenvironment{shCard}[1][]{%" in s.p.render() and "% from " in s.p.render()


def test_environment_arguments_are_keywords_and_checked():
    s = shop()
    with pytest.raises(TypeError, match="unexpected"):
        s.Card(nope="x")

    class Needs(Environment):
        """A required argument."""

        begin = "#a"
        end = "e"

        a: Text

    with pytest.raises(TypeError, match="missing"):
        Needs()
    with refused("TM-M004"):

        class IntArg(Environment):
            """A dict field."""

            begin = "b"
            end = "e"

            n: dict[str, str] | None = None


def test_the_grammar_reports_every_problem_with_a_path():
    s = shop()
    card = s.Card(s.Fact("a"), s.Name("n"), s.Fact("b"), s.Fact("c"), s.Fact("d"), s.Slot("s"), s.Fact("e"))
    out = [(v.code, v.path) for v in card.violations()]
    assert out == [
        ("TM-C002", "Card"),  # no Name first
        ("TM-C002", "Card"),  # and so only one Fact where two are needed
        ("TM-C001", "Card/Name[1]"),
        ("TM-C001", "Card/Fact[2]"),
        ("TM-C001", "Card/Fact[3]"),
        ("TM-C001", "Card/Fact[4]"),
        ("TM-C001", "Card/Slot[5]"),
        ("TM-C001", "Card/Fact[6]"),
    ]
    assert card.violations()[0].hint.startswith("allowed: 1-1 Name, 2-3 Fact, 0-3 Slot")
    assert [v.code for v in s.Card(s.Name("n"), s.Fact("a")).violations()] == ["TM-C002"]
    assert [v.path for v in s.Card(s.Name("n"), s.Fact("a"), s.Fact("b"), "stray").violations()] == ["Card/str[3]"]  # pyright: ignore[reportArgumentType]


def test_nested_environments_validate_their_own_children():
    p = Package("n", prefix="n")

    @p.command
    class Leaf(Command):
        """Leaf."""

        body = "x"

    @p.environment
    class Inner(Environment):
        """Inner."""

        begin = "b"
        end = "e"

        children = [Leaf.times.at_least_one()]

    @p.environment
    class Outer(Environment):
        """Outer."""

        begin = "b"
        end = "e"

        children = [Inner.times(1), Leaf.times.any()]

    assert Outer(Inner(Leaf()), Leaf()).violations() == []
    assert [v.path for v in Outer(Inner()).violations()] == ["Outer/Inner[0]"]
    assert Outer().violations() == []
    with pytest.raises(ExceptionGroup) as info:
        Outer(Inner()).render()
    assert codes(info) == ["TM-C002"] and info.value.exceptions[0].path == "Outer/Inner[0]"  # pyright: ignore[reportAttributeAccessIssue]


def test_grammar_terms_and_their_refusals():
    s = shop()
    assert s.Fact.times.any() == Repeat(s.Fact, 0, None) == s.Fact.times(None)
    assert s.Fact.times.at_least_one() == Repeat(s.Fact, 1, None) == s.Fact.times(1, None)
    assert s.Fact.times(3) == Repeat(s.Fact, 0, 3) and s.Fact.times(1, 4) == Repeat(s.Fact, 1, 4)
    assert [
        str(x)
        for x in (
            s.Fact.times(1),
            s.Fact.times(None),
            s.Fact.times(1, None),
            s.Fact.times(2, 2),
            s.Fact.times(1, 1),
        )
    ] == ["0-1 Fact", "0-any Fact", "1-any Fact", "2-2 Fact", "1-1 Fact"]
    for bad in ((3, 2), (-1,), (-1, 2), (0,), (1.5,), (1, "x"), ("x",), (1, 2.5), (), (1, 2, 3), (None, 3)):
        with refused("TM-M020"):
            s.Fact.times(*bad)  # pyright: ignore[reportArgumentType]
    with refused("TM-M020"):

        class Bad(Environment):
            """Strings are not components."""

            begin = "b"
            end = "e"

            children = ["Name"]  # pyright: ignore[reportAssignmentType]


def test_environment_bodies_are_found_linted_and_attributed():
    p = Package("e", prefix="e")
    with refused("TM-M006") as info:

        @p.environment
        class NoBodies(Environment):
            """No files."""

    assert "no begin" in str(info.value)
    with refused("TM-M018"):

        @p.environment
        class EndHole(Environment):
            """End cannot read arguments."""

            begin = "#a"
            end = "#a"

            a: Text

    with refused("TM-M011"):

        @p.environment
        class Open(Environment):
            """Braces."""

            begin = "{"
            end = "}"

    with refused("TM-M010"):

        @p.environment
        class Forgot(Environment):
            """Never uses its argument."""

            begin = "x"
            end = "y"

            a: Text

    @p.environment
    class Fine(Environment):
        """Hash pairs are literal in both."""

        begin = "\\relax ##"
        end = "##"

    assert "(body: inline)" in p.render()


def test_a_body_that_names_an_undeclared_component_is_refused_in_environments_too():
    p = Package("e", prefix="e")

    @p.environment
    class Env(Environment):
        """Names a command that is not there."""

        begin = "\\eMissing"
        end = "x"

    with refused("TM-M015"):
        p.render()


def test_a_document_is_complete_and_deterministic():
    s = shop()
    tex = s.p.document(
        Document(
            s.Card(s.Name("Rex"), s.Fact("50% sure"), s.Fact("b")),
            s.Fact("after"),
            settings=[s.Gap(Length("3mm")), s.Ink(Gray(0.5)), s.Tight(True)],
            options=["a4paper", "11pt"],
        )
    )
    assert tex == s.p.document(
        Document(
            s.Card(s.Name("Rex"), s.Fact("50% sure"), s.Fact("b")),
            s.Fact("after"),
            settings=[s.Gap(Length("3mm")), s.Ink(Gray(0.5)), s.Tight(True)],
            options=["a4paper", "11pt"],
        )
    )
    assert tex.splitlines()[1:] == [
        "\\documentclass[a4paper,11pt]{article}",
        "\\usepackage{shop}",
        "\\setlength{\\shGap}{3mm}",
        "\\definecolor{sh-ink}{gray}{0.5}",
        "\\shTighttrue",
        "\\begin{document}",
        "\\begin{shCard}",
        "\\shName{Rex}",
        "\\shFact{50\\% sure}",
        "\\shFact{b}",
        "\\end{shCard}",
        "\\shFact{after}",
        "\\end{document}",
    ]
    assert tex.startswith("% shop document -- generated with texmodel ")
    assert s.p.document().splitlines()[1] == "\\documentclass{article}"


def test_a_document_reports_every_problem_at_once():
    s = shop()
    with pytest.raises(ExceptionGroup) as info:
        s.p.document(Document(s.Card(), s.Fact(Raw("x")), options=["ok", "a]b", ""]))  # pyright: ignore[reportArgumentType]
    assert sorted(codes(info)) == ["TM-C002", "TM-C002", "TM-C003", "TM-C006", "TM-C006"]


def test_settings_are_checked_against_the_declared_type():
    s = shop()
    for make in (lambda: s.Gap("3mm"), lambda: s.Tight(1), lambda: s.Ink(Length("1mm"))):
        with refused("TM-M014"):
            make()
    assert repr(s.Gap(Length("3mm"))) == "Gap(Length(value=Decimal('3'), unit='mm'))"


def test_the_document_class_is_validated():
    with refused("TM-P004"):
        Package("p", prefix="p", document_class="Not Valid")
