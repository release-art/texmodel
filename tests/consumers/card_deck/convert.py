"""`cards.toml` and `project.toml` to texmodel nodes and the preamble: the consumer's side of Gate B.

Deck policies live here, not in the library: a typographic apostrophe prints straight, and a title is set in title case.
"""

import pathlib
import tomllib
from typing import Any

from texmodel.package import PreambleSlots
from texmodel.plan import Plan
from texmodel.preamble import InputPath
from texmodel.types import Raw

from . import legacy, model

HERE = pathlib.Path(__file__).parent


def load(folder: pathlib.Path = HERE) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    project = tomllib.loads((folder / "project.toml").read_text(encoding="utf-8"))
    return project, tomllib.loads((folder / "cards.toml").read_text(encoding="utf-8"))["cards"]


def text(value: str) -> str:
    return value.replace("’", "'")


def preamble(project: dict[str, Any]) -> PreambleSlots:
    return PreambleSlots(
        before_class=(Raw(r"\def\deckBeforeClass{yes}"),),
        before_package=(InputPath("res/"),),
        after_package=(
            *(Raw(rf"\newcommand{{{label.value.tex}}}{{{model.SHOWN[label]}}}") for label in model.SlotLabel),
        ),
    )


def settings(project: dict[str, Any]) -> list[model.DeckName]:
    return [model.DeckName(project["deck_name"])]


def card(number: int, source: dict[str, Any]) -> model.Card:
    by_label: dict[str, list[str]] = {}
    for line in source["one_liners"]:
        by_label.setdefault(line["label"], []).append(text(line["text"]))
    slots = (
        model.LabelledSlot(model.SlotLabel[label.upper()], " ".join(by_label[label]))
        for label in ("sound", "spot", "where")
    )
    return model.Card(
        model.CardFront(model.CardImage(Raw(legacy.image(number, source)))),
        model.CardBack(
            model.Name(legacy.card_title(text(source["name"]))), *map(model.LeadFact, by_label["fact"]), *slots
        ),
    )


def nodes(folder: pathlib.Path = HERE) -> tuple[model.Card, ...]:
    return tuple(card(n, c) for n, c in enumerate(load(folder)[1], 1))


def body(cards: list[dict[str, Any]]) -> tuple[model.CardHeader | model.Card, ...]:
    """Each card under its audit block."""
    return tuple(node for n, c in enumerate(cards, 1) for node in (model.CardHeader(c["name"], c["id"]), card(n, c)))


def plan(folder: pathlib.Path = HERE) -> Plan:
    project, cards = load(folder)
    return model.pkg.plan(*body(cards), settings=settings(project), preamble=preamble(project))


def deck(folder: pathlib.Path = HERE) -> str:
    return plan(folder).text
