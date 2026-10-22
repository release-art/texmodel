"""A business card: commands, values of every kind, and an environment whose children follow a grammar."""

from texmodel.body import TemplateRef
from texmodel.components import Command, Environment, Value
from texmodel.package import Package
from texmodel.types import CMYK, RGB, Colour, Length, Text

pkg = Package("business-card", prefix="bc", version="1.0.0", date="2026/10/22", description="Business cards")


@pkg.value
class Gap(Value[Length]):
    """Space under each line."""

    default = Length("2mm")


@pkg.value
class CardWidth(Value[Length]):
    """Width of a card."""

    default = Length("85mm")


@pkg.value
class Ink(Value[Colour]):
    """The text colour (CMYK, so it stays black ink in print)."""

    default = CMYK(0, 0, 0, 0.95)


@pkg.value
class Accent(Value[Colour]):
    """The accent colour (RGB: screen only)."""

    default = RGB(0.7, 0.1, 0.2)


@pkg.value
class Compact(Value[bool]):
    """Tighten the layout."""

    default = False


@pkg.command
class Name(Command):
    """The person's name, set as the title."""

    text: Text

    body = TemplateRef("name.tex")


@pkg.command
class Title(Command):
    """A job title in the accent colour."""

    text: Text
    body = r"""
        \par\noindent{\color{bc-accent}#text}\par
    """


@pkg.command
class Contact(Command):
    """One contact line; the label, if any, prints in bold before it."""

    text: Text
    label: Text | None = None

    body = TemplateRef("contact.tex")


@pkg.environment
class Card(Environment):
    """One card: a name, an optional title and one to three contact lines."""

    begin = TemplateRef("card.begin.tex")
    end = TemplateRef("card.end.tex")

    children = [Name, Title.times(1), Contact.times(1, 3)]


ada = Card(
    Name("Ada Lovelace"),
    Title("Analyst"),
    Contact("ada@example.org", label="Mail"),
    Contact("+44 20 7946 0000"),
)

# Settings change values for the whole document; hostile text is escaped; an optional `]` is wrapped.
compact = Card(
    Name("R&D: 50% of $5"),
    Contact(r"path_to\file {x}", label="a]b"),
)

documents = {
    "ada": pkg.document(ada),
    "compact": pkg.document(
        compact,
        settings=[Compact(True), Gap(Length("1.5mm")), Accent(RGB(0, 0.4, 0.8))],
        options=["a4paper", "11pt"],
    ),
}
