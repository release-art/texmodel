"""The card grammar of `res/card-deck.sty`, declared (M9) so documents are checked. Nothing here renders TeX for it."""

import enum

from texmodel.components import Command, Environment
from texmodel.package import Package
from texmodel.types import Choice, Raw, Text

pkg = Package("card-deck", prefix="cd", adopted=True)


@enum.unique
class SlotLabel(Choice):
    """A labelled slot's label: each member is the macro the deck defines for it."""

    FACT = Raw(r"\deckParamFactFact")
    SOUND = Raw(r"\deckParamFactSound")
    SPOT = Raw(r"\deckParamFactSpot")
    WHERE = Raw(r"\deckParamFactWhere")


SHOWN = {SlotLabel.FACT: "Fact", SlotLabel.SOUND: "Sound", SlotLabel.SPOT: "Spot", SlotLabel.WHERE: "Where"}


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
    """A fact whose label runs in at its start; the label is a `SlotLabel`."""

    label: SlotLabel
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
