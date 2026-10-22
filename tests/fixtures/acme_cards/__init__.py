"""A small package used by the tests: the committed `generated/acme-cards.sty` is its golden output."""

from texmodel.components import Command, Environment, TemplateRef, Value
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

    body = TemplateRef("name.tex")


@pkg.command
class Fact(Command):
    """One short sentence under the title."""

    text: Text

    body = TemplateRef("fact.tex")


@pkg.command
class Slot(Command):
    """A labelled paragraph; the label prints as its heading."""

    text: Text
    label: Text | None = None

    body = TemplateRef("slot.tex")


@pkg.command
class Rule(Command):
    """A thin horizontal rule."""

    body = r"\par\noindent\rule{\linewidth}{0.4pt}\par"


@pkg.environment
class CardBack(Environment):
    """The back face of a card."""

    begin = TemplateRef("card_back.begin.tex")
    end = TemplateRef("card_back.end.tex")

    children = [Name, Fact * (2, 3), Slot * (0, 3)]
