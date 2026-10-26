"""Reading a stub's call back: the typed value each argument text stands for."""

import enum
import re
import string

import pytest
from hypothesis import (
    given,
    strategies as st,
)

from texmodel._internal.read import detokenized
from texmodel.body import RefKind
from texmodel.components import Command
from texmodel.interface import PAREN, SQUARE, ColourName, Flag, Star, arg
from texmodel.keys import PGFKEYS
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.plan import FieldEdit
from texmodel.testing import Call, expand, read_call
from texmodel.types import CMYK, Choice, Length, PdfString, Raw, Text, escape

pkg = Package("reader", prefix="rd")


@enum.unique
class Level(Choice):
    LOW = Raw(r"\rdLow")
    HIGH = Raw(r"\rdHigh")


@enum.unique
class Mood(Choice):
    DRY = "high & dry"
    WET = "low"


class Opts(KeyVals, rules=PGFKEYS):
    center: Flag = False


@pkg.command
class Kinds(Command):
    """Every kind of argument."""

    text: Text
    width: Length
    count: int
    ratio: float
    on: bool
    level: Level
    mood: Mood
    at: tuple[int, int] = arg(PAREN)
    tags: list[Text] = arg(SQUARE)
    star: Star = arg(default=False)
    raw: Raw
    ink: CMYK
    colour: ColourName
    pdf: PdfString
    opts: Opts
    note: Text | None = None
    body = "#text #width #count #ratio #on #level #mood #at #tags #star #raw #ink #colour #pdf #opts #note"


def kinds(**changes):
    values = {
        "text": "a & b",
        "width": Length("3cm"),
        "count": 3,
        "ratio": 0.5,
        "on": True,
        "level": Level.LOW,
        "mood": Mood.DRY,
        "at": (1, -2),
        "tags": ["x", "y"],
        "star": True,
        "raw": Raw(r"\textbf{x}"),
        "ink": CMYK(0, 0, 0, 1),
        "colour": "blue!50",
        "pdf": "p",
        "opts": Opts(center=True),
    }
    return Kinds(**{**values, **changes})


def read(**changes) -> dict[str, FieldEdit]:
    (call,) = [c for c in expand(kinds(**changes), stubs=[Kinds]) if isinstance(c, Call)]
    return {f.arg: f for f in read_call(Kinds, call)}


def test_each_kind_reads_back_to_the_value_it_was_written_from():
    got = read()
    assert {name: f.value for name, f in got.items()} == {
        "text": "a & b", "width": Length("3cm"), "count": 3, "ratio": 0.5, "on": True,
        "level": Level.LOW, "mood": Mood.DRY,
        "at": (1, -2), "tags": ["x", "y"], "star": True, "raw": Raw(r"\textbf {x}"),
        "ink": (0.0, 0.0, 0.0, 1.0), "colour": "blue!50", "pdf": None, "opts": None, "note": None,
    }  # fmt: skip
    assert all(
        f.violation is None for f in got.values()
    )  # a record reads as a plain tuple; a key list and a PDF string are unsaid
    assert read(level=Level.HIGH)["level"].value is Level.HIGH and read(mood=Mood.WET)["mood"].value is Mood.WET
    assert read(star=False)["star"].value is False and read(on=False)["on"].value is False


@pytest.mark.parametrize(
    ("field", "text"),
    [
        ("text", r"a \today"), ("text", "{x}"), ("width", "3 parsecs"), ("count", "three"), ("ratio", "1e3"),
        ("on", "maybe"), ("level", r"\rdMid"), ("mood", "damp"), ("at", "1"), ("star", "yes"), ("colour", "!!"),
    ],
)  # fmt: skip
def test_a_text_that_is_not_a_value_of_the_type_is_a_violation_at_the_field(field, text):
    (call,) = [c for c in expand(kinds(), stubs=[Kinds]) if isinstance(c, Call)]
    names = list(read_call(Kinds, call))
    args = tuple(text if f.arg == field else f.found for f in names)
    (bad,) = [f for f in read_call(Kinds, Call(call.name, args)) if f.arg == field]
    assert bad.value is None and bad.violation and (bad.violation.code, bad.violation.path) == ("TM-C021", field)


def test_a_length_is_read_with_spaces_or_as_a_tex_expression():
    one = Call("rdKinds", tuple("3 cm" if f.arg == "width" else f.found for f in read().values()))
    assert {f.arg: f.value for f in read_call(Kinds, one)}["width"] == Length("3cm")
    two = Call("rdKinds", tuple(r"2\linewidth " if f.arg == "width" else f.found for f in read().values()))
    assert str({f.arg: f.value for f in read_call(Kinds, two)}["width"]) == r"2\linewidth"


def test_an_empty_optional_has_no_value_and_a_closing_call_has_no_arguments():
    assert read()["note"] == FieldEdit("note", "")
    assert read(note="n")["note"].value == "n"
    assert read_call(Kinds, Call("rdKinds", (), RefKind.CLOSE)) == ()


def test_an_empty_list_reads_as_empty():
    assert read(tags=[])["tags"].value == []


# --- laws ---------------------------------------------------------------------------------------------------------


@given(st.text(string.printable))
def test_text_reads_back_up_to_the_spaces_tex_collapses(text):
    assert read(text=text)["text"].value == re.sub(r"\s+", " ", text.lstrip())


@given(st.integers(-(10**9), 10**9), st.floats(-1e6, 1e6, allow_nan=False))
def test_numbers_read_back(count, ratio):
    got = read(count=count, ratio=ratio)
    assert got["count"].value == count and got["ratio"].value == pytest.approx(ratio, abs=1e-5)


@given(st.text(string.printable))
def test_detokenized_is_idempotent(text):
    assert detokenized(detokenized(escape(text))) == detokenized(escape(text))
