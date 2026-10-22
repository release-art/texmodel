"""`Choice` (T1): a closed set whose members carry their TeX; data names a member."""

import enum

import pytest

from texmodel.components import Command
from texmodel.package import Package
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import Choice, Raw, Text

from .test_document import refused


@enum.unique
class Kind(Choice):
    A = Raw(r"\alpha")
    B = Raw(r"\beta")


@enum.unique
class Words(Choice):
    ONE = "1 & 2"
    TWO = "50%"


pkg = Package("choice-demo", prefix="ch")


@pkg.command
class Mark(Command):
    """A mark."""

    body = "#kind #text"
    kind: Kind
    text: Text


@pkg.command
class Say(Command):
    """Words."""

    body = "#words"
    words: Words | None = None


def test_a_raw_member_passes_through_and_a_str_member_is_escaped():
    assert Mark(Kind.B, "x").render() == r"\chMark{\beta}{x}"
    assert Say(words=Words.ONE).render() == r"\chSay[1 \& 2]"
    assert Say().render() == r"\chSay"


def test_validate_names_the_choices_when_the_value_is_not_a_member():
    (v,) = Mark("\\alpha", "x").validate()  # type: ignore[arg-type]
    assert v.code == "TM-C003" and "one of ['A', 'B']" in v.message and v.path == "Mark.kind"
    assert Mark(Kind.A, "x").validate() == []


def test_repr_is_the_expression_that_builds_it():
    assert repr(Mark(Kind.A, "x")) == "Mark(Kind.A, 'x')"


def test_members_must_be_all_raw_or_all_str_and_not_aliases():
    class Mixed(Choice):
        A = Raw("x")
        B = "y"

    class Alias(Choice):
        A = Raw("x")
        B = Raw("x")

    for bad in (Mixed, Alias):
        with refused("TM-M024"):

            class Holder(Command):
                """Bad."""

                kind: bad  # type: ignore[valid-type]


def test_data_names_a_member_and_comes_back_as_its_name():
    node = from_dict(Mark, {"kind": "B", "text": "x"})
    assert node == Mark(Kind.B, "x") and to_dict(node) == {"type": "Mark", "kind": "B", "text": "x"}
    assert from_dict(Mark, {"kind": Kind.A, "text": "x"}) == Mark(Kind.A, "x")
    assert from_dict(Say, {"words": "TWO"}) == Say(words=Words.TWO)


def test_data_that_names_no_member_says_which_exist():
    with pytest.raises(ExceptionGroup) as group:
        from_dict(Mark, {"kind": "C", "text": "x"})
    (error,) = group.value.exceptions
    assert error.path == "Mark.kind" and "one of ['A', 'B']" in str(error)  # pyright: ignore[reportAttributeAccessIssue]


def test_the_schema_lists_the_member_names():
    assert json_schema(Mark)["properties"]["kind"] == {"enum": ["A", "B"], "title": "Kind", "type": "string"}
