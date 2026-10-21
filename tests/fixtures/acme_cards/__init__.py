"""A small package used by the tests: the committed `generated/acme-cards.sty` is its golden output."""

from texmodel.components import Command, Environment, Value
from texmodel.package import Package
from texmodel.types import CMYK, Bool, Colour, Length, Text

pkg = Package("acme-cards", prefix="ac", version="1.4.0", date="2026/10/21", description="Cards for Acme")


@pkg.value
class FactGap(Value[Length]):
    """Space under each fact."""

    default = Length("2mm")


@pkg.value
class Ink(Value[Colour]):
    """The text colour."""

    default = CMYK(0, 0, 0, 0.95)


@pkg.value
class Compact(Value[Bool]):
    """Tighten the layout."""

    default = False


@pkg.command
class Name(Command):
    """The subject's name, set as the title."""

    text: Text


@pkg.command
class Fact(Command):
    """One short sentence under the title."""

    text: Text


@pkg.command
class Slot(Command):
    """A labelled paragraph; the label prints as its heading."""

    text: Text
    label: Text | None = None


@pkg.command
class Rule(Command, body=r"\par\noindent\rule{\linewidth}{0.4pt}\par"):
    """A thin horizontal rule."""


@pkg.environment
class CardBack(Environment):
    """The back face of a card."""

    children = [Name, Fact * (2, 3), Slot * (0, 3)]
