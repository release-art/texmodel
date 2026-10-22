"""The card grammar of `res/card-deck.sty`, declared (M9) so documents are checked. Nothing here renders TeX for it."""

import enum

from texmodel.components import Command, Environment
from texmodel.package import Package
from texmodel.types import Raw, Text

pkg = Package("card-deck", prefix="cd", adopted=True)


@enum.unique
class SlotLabel(enum.Enum):
    """A labelled slot's label: the macro the deck defines for it, and the words that print."""

    FACT = (r"\deckParamFactFact", "Fact")
    SOUND = (r"\deckParamFactSound", "Sound")
    SPOT = (r"\deckParamFactSpot", "Spot")
    WHERE = (r"\deckParamFactWhere", "Where")

    @property
    def macro(self) -> Raw:
        return Raw(self.value[0])

    @property
    def shown(self) -> str:
        return self.value[1]


@pkg.command
class DeckName(Command):
    """The deck name; set once per deck with `\\renewcommand`."""


@pkg.command
class CardImage(Command):
    """A card face's picture, by path."""

    path: Raw


@pkg.command
class Name(Command):
    """The card's title; exactly one a back."""

    text: Text


@pkg.command
class LeadFact(Command):
    """A fact under the title; two or three a back."""

    text: Text


@pkg.command
class LabelledSlot(Command):
    """A fact whose label runs in at its start; the label is a macro the deck defines (`SlotLabel`)."""

    label: Raw
    text: Text


@pkg.command
class TalkAboutMe(Command):
    """A question, with an optional answer; any number a back."""

    question: Text
    answer: Text | None = None


@pkg.environment
class CardFront(Environment):
    """The front face: its picture."""

    children = [CardImage]


@pkg.environment
class CardBack(Environment):
    """The back face, in the order the package prints it."""

    children = [Name, LeadFact.times(2, 3), LabelledSlot.times(3), TalkAboutMe.times.any()]


@pkg.environment
class Card(Environment):
    """One card: its front, then its back."""

    children = [CardFront, CardBack]
