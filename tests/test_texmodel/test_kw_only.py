"""Fields are passed by keyword unless a class says `kw_only=False` (the dataclass word; type checkers read it too)."""

import pytest

from texmodel.components import Command, Environment, Passthrough, field
from texmodel.interface import arg
from texmodel.package import Package
from texmodel.types import Raw, Text

pkg = Package("kw-demo", prefix="kw")


@pkg.command
class Fact(Command):
    """A fact."""

    text: Text
    note: Text | None = None
    body = r"#text#note"


@pkg.command
class Slot(Command, kw_only=False):
    """A slot that reads well positionally."""

    text: Text
    label: Text | None = arg(default=None)
    body = r"#text#label"


@pkg.command
class Special(Slot):
    """A subclass keeps its base's choice."""

    body = r"#text#label"


@pkg.command
class Plain(Fact, kw_only=True):
    """A subclass may choose again."""

    body = r"#text#note"


@pkg.environment
class Box(Environment):
    """Fields by keyword, children positional."""

    title: Text = field(default="")
    begin = r"\begin{center}#title"
    end = r"\end{center}"


def test_fields_are_keyword_only_by_default():
    assert Fact(text="a").text == "a" and Fact(text="a", note="n").note == "n"
    with pytest.raises(TypeError, match=r"takes 0 positional argument\(s\), got 1.*kw_only=False"):
        Fact("a")  # pyright: ignore[reportCallIssue]
    with pytest.raises(TypeError, match="missing arguments"):
        Fact()  # pyright: ignore[reportCallIssue]


def test_a_class_can_opt_in_to_positional_fields():
    assert Slot("a").text == "a" and Slot("a", label="L").label == "L"
    with pytest.raises(TypeError, match="takes 1 positional argument"):
        Slot("a", "L")  # pyright: ignore[reportCallIssue]
    with pytest.raises(TypeError, match=r"multiple values for \['text'\]"):
        Slot("a", text="b")  # pyright: ignore[reportCallIssue]


def test_the_choice_is_inherited_and_can_be_changed_again():
    assert Special("a").text == "a"
    assert Plain(text="a").text == "a"
    with pytest.raises(TypeError, match="kw_only=False"):
        Plain("a")  # pyright: ignore[reportCallIssue]


def test_repr_writes_the_call_the_class_allows():
    assert repr(Fact(text="a", note="n")) == "Fact(text='a', note='n')"
    assert repr(Slot("a", label="L")) == "Slot('a', label='L')"


def test_environment_children_are_positional_and_its_fields_keyword():
    box = Box(Fact(text="a"), title="T")
    assert box.title == "T" and box.content == (Fact(text="a"),)


def test_passthrough_keeps_its_positional_argument():
    assert Passthrough(Raw("x")).tex == Raw("x")
