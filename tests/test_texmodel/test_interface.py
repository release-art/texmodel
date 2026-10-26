"""Macro interfaces: slots, groups, value types, xparse definitions, the scanner."""

import dataclasses
import enum
import typing

import pydantic
import pytest
from hypothesis import (
    given,
    strategies as st,
)

from texmodel._internal.render import canonical, newcommand_fits, signature, xparse_spec
from texmodel._internal.scan import scan_declarations, xparse_letters
from texmodel.body import Hole
from texmodel.components import Command, Environment
from texmodel.errors import ValidationError
from texmodel.interface import (
    ANGLE,
    PAREN,
    SQUARE,
    ColourName,
    Delimiter,
    FieldNotes,
    Gap,
    SlotGroup,
    Star,
    Token,
    arg,
    body_of,
)
from texmodel.keys import KeyRules
from texmodel.package import Package
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.testing import Call, expand, stub_tex
from texmodel.types import CMYK, RGB, Choice, Colour, Length, LengthExpr, PdfString, Raw, Text

from .test_document import refused


def only_calls(items):
    return [c for c in items if isinstance(c, Call)]


def pkg():
    return Package("iface", prefix="", builtin=True, adopted=True)


# --- delimiters, tokens and rules ----------------------------------------------------------------------------------


@pytest.mark.parametrize("pair", [("ab", ")"), ("(", "("), ("a", "b"), (" ", ")"), ("\\", "]"), ("(", "%")])
def test_a_delimiter_is_two_different_single_non_alphanumeric_characters(pair):
    with refused("TM-M036"):
        Delimiter(*pair)


def test_a_token_is_one_non_alphanumeric_character_and_rules_are_consistent():
    assert Token("+").char == "+"
    for bad in ("ab", "a", " ", "{"):
        with refused("TM-M036"):
            Token(bad)
    with refused("TM-M036"):
        KeyRules(assign=",")
    with refused("TM-M036"):
        KeyRules(assign="")


# --- slots -----------------------------------------------------------------------------------------------------------


def make_box():
    p = pkg()

    @p.command
    class MakeBox(Command):
        r"""`\makebox[3cm][c]{x}`."""

        cs = "makebox"
        width: Length | None = arg(SQUARE, fill="", default=None)
        pos: Text | None = arg(SQUARE, default=None)
        text: Text

    return MakeBox


def test_optional_slots_are_written_in_order_and_a_skipped_one_is_filled():
    box = make_box()
    assert box("x").render() == r"\makebox{x}"
    assert box("x", width=Length("3cm")).render() == r"\makebox[3cm]{x}"
    assert box("x", pos="c").render() == r"\makebox[][c]{x}"  # the width is unset: `fill=""`
    assert box("x", width=Length("3cm"), pos="c").render() == r"\makebox[3cm][c]{x}"
    assert repr(box("x", pos="c")) == "MakeBox('x', pos='c')"


def test_two_optional_slots_are_defined_with_xparse_and_one_is_not():
    p = Package("iface-gen", prefix="ig")

    @p.command
    class Two(Command):
        """Two optional arguments."""

        a: Text | None = arg(SQUARE, fill="", default=None)
        b: Text | None = arg(SQUARE, default=None)
        c: Text

        body = r"\textbf{#a}\textit{#b}#c"

    @p.command
    class One(Command):
        """One."""

        c: Text
        a: Text | None = None

        body = "#a#c"

    sty = p.render()
    assert r"\NewDocumentCommand{\igTwo}{O{}O{}m}{%" in sty
    assert r"\textbf{#1}\textit{#2}#3" in sty
    assert r"\newcommand{\igOne}[2][]{%" in sty and "#1#2" in sty  # unchanged: `\newcommand` can define it
    assert Two("x", b="y").render() == r"\igTwo[][y]{x}"
    assert signature(Two.__tm_args__) == "oom"
    assert newcommand_fits(One.__tm_args__) and not newcommand_fits(Two.__tm_args__)


def test_a_star_a_paren_slot_and_other_delimiters():
    p = pkg()

    @p.command
    class Section(Command):
        r"""`\section*[short]{long}`."""

        cs = "section"
        starred: Star = arg(default=False)
        short: Text | None = arg(SQUARE, default=None)
        title: Text

    @p.command
    class Put(Command):
        r"""`\put(1,2){x}`."""

        cs = "put"
        at: tuple[int, int] = arg(PAREN)
        text: Raw

    @p.command
    class Angle(Command):
        r"""`\only<2>{x}`."""

        cs = "only"
        overlay: Text | None = arg(ANGLE, default=None)
        text: Raw

    assert Section("T").render() == r"\section{T}"
    assert Section("T", starred=True).render() == r"\section*{T}"
    assert Section("T", starred=True, short="S").render() == r"\section*[S]{T}"
    assert Put(at=(1, 2), text=Raw("x")).render() == r"\put(1,2){x}"
    assert Angle(Raw("x"), overlay="2").render() == r"\only<2>{x}"
    assert repr(Section("T", starred=True)) == "Section('T', starred=True)"
    assert xparse_spec(Section.__tm_args__) == "sO{}m" and signature(Section.__tm_args__) == "som"
    assert xparse_spec(Put.__tm_args__) == "r()m" and xparse_spec(Angle.__tm_args__) == "D<>{}m"
    assert [a.name for a in Section.__tm_args__] == ["starred", "short", "title"]


def test_a_gap_that_is_refused_and_a_group_that_is_all_or_none():
    p = pkg()
    pair = SlotGroup("pair")

    @p.command
    class Strict(Command):
        """Skipping is refused."""

        cs = "strict"
        a: Text | None = arg(SQUARE, fill=Gap.REFUSE, default=None)
        b: Text | None = arg(SQUARE, default=None)
        c: Text

    @p.command
    class Grouped(Command):
        """Two slots written together."""

        cs = "grouped"
        a: Text | None = arg(PAREN, group=pair, default=None)
        b: Text | None = arg(SQUARE, group=pair, default=None)
        c: Text

    assert Strict("c", a="1").render() == r"\strict[1]{c}"
    assert [v.code for v in Strict("c", b="2").violations()] == ["TM-C005"]
    with pytest.raises(ExceptionGroup):
        Strict("c", b="2").render()
    assert Grouped("c").render() == r"\grouped{c}" and Grouped("c", a="1", b="2").render() == r"\grouped(1)[2]{c}"
    (v,) = Grouped("c", a="1").violations()
    assert v.code == "TM-C004" and "['b']" in v.message


def test_declaration_errors_of_a_signature():
    p = pkg()
    with refused("TM-M037"):

        class NoFill(Command):
            """Two optional, no fill."""

            cs = "nofill"
            a: Text | None = arg(SQUARE, default=None)
            b: Text | None = arg(SQUARE, default=None)

    with refused("TM-M038"):

        class RequiredInGroup(Command):
            """A required slot in a group."""

            cs = "reqgroup"
            a: Text = arg(PAREN, group=SlotGroup("g"))

    with refused("TM-M039"):

        class StarWithoutDefault(Command):
            """A token with no default."""

            cs = "nostar"
            starred: Star

    with refused("TM-M004"):

        class Unsupported(Command):
            """A set."""

            cs = "unsupported"
            a: set[int]

    assert p is not None


def test_signatures_compare_as_xparse_letters():
    assert [canonical(s) for s in ("", "[1]", "[2][]", "[3]")] == ["", "m", "om", "mmm"]
    assert canonical("omm") == "omm"


# --- values ----------------------------------------------------------------------------------------------------------


class Place(typing.NamedTuple):
    x: Length
    y: Length


@dataclasses.dataclass(frozen=True)
class Size:
    w: int
    h: int


class Pair(pydantic.BaseModel):
    a: Text
    b: int


@enum.unique
class Align(Choice):
    LEFT = Raw("l")
    RIGHT = Raw("r")


def test_each_value_type_is_written_and_checked():
    p = pkg()

    @p.command
    class Everything(Command):
        """One of each."""

        cs = "everything"
        length: Length
        n: int
        flag: bool
        colour: Colour
        name: ColourName
        align: Align
        place: Place
        size: Size
        pair: Pair
        many: list[int]
        fixed: tuple[Length, Text]
        hole: PdfString
        ratio: float

    node = Everything(
        Length("2mm"),
        3,
        True,
        CMYK(0, 0, 0, 1),
        "blue!50",
        Align.RIGHT,
        Place(Length("1cm"), LengthExpr(r"\linewidth")),
        Size(2, 3),
        Pair(a="a & b", b=2),
        [1, 2],
        (Length("1pt"), "x_y"),
        "A (b)",
        0.50,
    )
    assert node.render() == (
        r"\everything{2mm}{3}{true}{0,0,0,1}{blue!50}{r}{1cm,\linewidth}{2,3}{a \& b,2}{1,2}{1pt,x\_y}"
        r"{\detokenize{A \050b\051}}{0.5}"
    )
    assert node.violations() == []
    bad = Everything("2mm", 3.5, 1, RGB(0, 0, 0), "9", "right", (1, 2), Size(1, "x"), (1, 2), [1, "x"], (1,), 3, True)  # pyright: ignore[reportArgumentType]
    assert {v.path.rsplit(".", 1)[1] for v in bad.violations()} == {
        "length", "n", "flag", "name", "align", "place", "size", "pair", "many", "fixed", "hole", "ratio",
    }  # fmt: skip
    assert Everything.__tm_args__[0].body.describe() == "Length"
    assert Everything.__tm_args__[7].body.describe().startswith("tuple of")
    assert [a.body.kind.value for a in Everything.__tm_args__][:4] == ["Length", "int", "bool", "Colour"]


def test_a_length_expression_is_a_length_in_tex_and_has_no_size():
    expr = Length.expr(r"0.5\textwidth")
    assert isinstance(expr, Length) and str(expr) == r"0.5\textwidth"
    with refused("TM-M016"):
        expr.inches  # noqa: B018
    with refused("TM-M016"):
        Length.expr("  ")
    with pytest.raises(ValidationError):
        Length.expr("{")
    assert Length.expr(Raw(r"\dimexpr 1pt\relax")).tex == r"\dimexpr 1pt\relax"


def test_a_length_in_data_is_a_string_or_an_expression():
    adapter = pydantic.TypeAdapter(Length)
    assert adapter.validate_python("2mm") == Length("2mm")
    assert adapter.validate_python({"expr": r"\linewidth"}) == Length.expr(r"\linewidth")
    assert adapter.validate_python(Length("1pt")) == Length("1pt")
    assert adapter.dump_python(Length("2mm"), mode="json") == "2mm"
    assert adapter.dump_python(Length.expr(r"\x"), mode="json") == {"expr": r"\x"}
    for bad in (3, "2 furlongs", {"expr": 3}, {"other": "x"}):
        with pytest.raises(pydantic.ValidationError):
            adapter.validate_python(bad)


def test_the_rest_of_the_value_helpers():
    from texmodel._internal.values import value_text
    from texmodel.interface import Item, OptionalValue

    token = body_of(Star)
    assert value_text(token, True) == "*" and value_text(token, False) == ""  # pyright: ignore[reportArgumentType]
    assert body_of(Item[int]) == body_of(int) == body_of(OptionalValue[int])
    assert body_of(typing.Annotated[int, "other"]) == body_of(int)
    assert body_of(list[typing.Annotated[set[int], "x"]]) is None

    class Odd(typing.NamedTuple):
        a: set[int]

    assert body_of(Odd) is None
    assert FieldNotes("old") in arg(renamed_from="old").metadata
    assert scan_declarations(r"\NewDocumentCommand{\cdOpen}{m", "cd") == {"cdOpen": "?"}


def test_body_of_reads_the_field_types_and_refuses_others():
    assert body_of(Length | None) is not None and body_of(Colour | None) is not None  # pyright: ignore[reportOptionalOperand]
    assert body_of(int | str) is None and body_of(set[int]) is None and body_of(list[set[int]]) is None
    assert body_of(tuple[set[int], int]) is None and body_of(tuple[()]) is None
    assert body_of(tuple[int, ...]) is not None and body_of(bytes) is None


def test_data_round_trips_through_the_new_types():
    p = pkg()

    @p.command
    class Box(Command):
        """A box."""

        cs = "boxed"
        width: Length
        at: Place
        many: list[int]
        colour: Colour | None = None

    node = Box(Length("2mm"), Place(Length("1cm"), Length.expr(r"\linewidth")), [1, 2], colour=CMYK(0, 0, 0, 1))
    data = to_dict(node)
    assert data == {
        "type": "Box",
        "width": "2mm",
        "at": ["1cm", {"expr": r"\linewidth"}],
        "many": [1, 2],
        "colour": {"c": 0.0, "m": 0.0, "y": 0.0, "k": 1.0},
    }
    assert from_dict(Box, data) == node
    assert json_schema(Box)["properties"]["width"]["anyOf"][0] == {"type": "string"}


def test_an_environment_takes_the_same_slots():
    p = Package("iface-env", prefix="ie")

    @p.environment
    class Frame(Environment, unused=("starred",)):
        """A frame."""

        begin = r"\begin{center}#title#label"
        end = r"\end{center}"
        starred: Star = arg(default=False)
        title: Text | None = arg(SQUARE, fill="", default=None)
        label: Text | None = arg(SQUARE, default=None)

    assert r"\NewDocumentEnvironment{ieFrame}{sO{}O{}}{%" in p.render()
    assert Frame(label="L").render() == "\\begin{ieFrame}[][L]\n\\end{ieFrame}"
    assert Frame(starred=True).render() == "\\begin{ieFrame}*\n\\end{ieFrame}"


# --- references and stubs ----------------------------------------------------------------------------------------


def test_a_reference_checks_every_slot_kind_and_writes_it():
    p = Package("iface-ref", prefix="ir")

    @p.command
    class Base(Command):
        """A target."""

        starred: Star = arg(default=False)
        opt: Text | None = arg(SQUARE, default=None)
        n: int

        body = "#starred#opt#n"

    @p.command
    class Caller(Command):
        """Calls it."""

        n: int

        def body(self):
            yield Base.call(3, starred=True, opt="x")
            yield Base.call(Hole("n"))

    sty = p.render()
    assert r"\irBase*[x]{3}" in sty and r"\irBase{#1}" in sty
    with refused("TM-M026"):
        Base.call("three")
    with refused("TM-M026"):
        Base.call(3, starred="yes")


def test_stubs_log_the_slots_and_a_star_reads_as_the_xparse_boolean():
    p = Package("iface-stub", prefix="is")

    @p.command
    class Heading(Command, unused=("starred", "short")):
        """A heading."""

        starred: Star = arg(default=False)
        short: Text | None = arg(SQUARE, default=None)
        title: Text

        body = "#title"

    @p.command
    class Page(Command):
        """Calls it."""

        title: Text

        def body(self):
            yield Heading.call(Hole("title"), starred=True)

    assert only_calls(expand(Page("T"), [Heading])) == [Call("isHeading", (r"\BooleanTrue ", "", "T"))]
    assert only_calls(expand(Heading("T"), [Heading])) == [Call("isHeading", (r"\BooleanFalse ", "", "T"))]
    tex = stub_tex([Heading])
    assert r"\RenewDocumentCommand{\isHeading}{sO{}m}" in tex and r"\detokenize{{#1}{#2}{#3}}" in tex


# --- the scanner and the interface check -----------------------------------------------------------------------


XPARSE = r"""
\NewDocumentCommand{\cdPlain}{m}{#1}
\NewDocumentCommand\cdStar{ s O{x} m }{#3}
\DeclareDocumentCommand{\cdParen}{ r() D<>{} t+ }{}
\NewDocumentEnvironment{cdBox}{o m}{}{}
\NewDocumentCommand{\cdOdd}{ v }{}
\newcommand{\cdOld}[2][]{}
% \NewDocumentCommand{\cdGone}{m}{}
\NewDocumentCommand{\cdOldAgain}{oo}{}
\NewDocumentCommand{\cdBroken}
"""


def test_the_scanner_reads_xparse_definitions_as_letters():
    found = scan_declarations(XPARSE, "cd")
    assert found == {
        "cdPlain": "m",
        "cdStar": "som",
        "cdParen": "r()d<>t+",
        "cdBox": "om",
        "cdOdd": "?",
        "cdOld": "[2][]",
        "cdOldAgain": "oo",
        "cdBroken": "?",
    }
    assert xparse_letters("m O{} +m") == "mom"
    assert xparse_letters("e{^_}") == "?" and xparse_letters("t") == "?"


def test_a_declared_xparse_signature_is_checked_against_the_hand_written_one():
    p = Package("iface-check", prefix="cd", adopted=True)

    @p.command
    class Star(Command):
        """Starred."""

        starred: typing.Annotated[bool, Token("*")] = arg(default=False)
        opt: Text | None = arg(SQUARE, default=None)
        text: Text

    @p.command
    class Old(Command):
        """Optional first."""

        text: Text
        opt: Text | None = None

    @p.environment
    class Box(Environment):
        """A box."""

        opt: Text | None = None
        text: Text

    @p.command
    class Plain(Command):
        """One argument."""

        text: Text

    sources = (
        r"\NewDocumentCommand{\cdStar}{sO{}m}{}\newcommand{\cdOld}[2][]{}\NewDocumentEnvironment{cdBox}{om}{}{}"
        r"\NewDocumentCommand{\cdPlain}{mm}{}"
    )
    (problem,) = p.check_interface(sources)
    assert problem.code == "TM-C011" and "cdPlain" in problem.message


@given(st.lists(st.sampled_from(["m", "o", "O{}", "s", "t+", "d()", "r()", "D<>{}"]), max_size=6))
def test_xparse_letters_are_stable_under_defaults(parts):
    spec = "".join(parts)
    letters = xparse_letters(spec)
    assert xparse_letters(letters) == letters
