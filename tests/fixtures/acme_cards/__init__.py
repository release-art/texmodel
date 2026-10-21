"""A small package used by the tests: the committed `generated/acme-cards.sty` is its golden output."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Text

pkg = Package("acme-cards", prefix="ac", version="1.4.0", date="2026/10/21", description="Cards for Acme")


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
