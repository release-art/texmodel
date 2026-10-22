"""A stand-in for the generator a consumer replaces: a template-style `deck.tex` writer with regex-free but ad hoc
escaping and title casing. It is the oracle for "the model prints what the generator printed"."""

import pathlib
import re
import tomllib
from typing import Any

HERE = pathlib.Path(__file__).parent
SMALL_WORDS = frozenset({"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to"})
CONV = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\^{}",
    "\\": r"\textbackslash{}",
    "<": r"\textless{}",
    ">": r"\textgreater{}",
    "’": "'",
}


def latex_escape(text: str) -> str:
    return "".join(CONV.get(c, c) for c in text)


def card_title(name: str) -> str:
    words = re.split(r"([ -])", name)
    return "".join(
        w if (i and w.lower() in SMALL_WORDS) or not w else w[0].upper() + w[1:] for i, w in enumerate(words)
    )


def image(number: int, card: dict[str, Any]) -> str:
    return f"images/{number:02d}-{'-'.join(card['name'].lower().split())}.jpg"


def render(project: dict[str, Any], cards: list[dict[str, Any]]) -> str:
    out = [
        "% ====================================================",
        f"% Deck: {project['name']} -- {len(cards)} cards",
        "% ====================================================",
        r"\def\deckBeforeClass{yes}",
        r"\documentclass{article}",
        r"\makeatletter\def\input@path{{res/}}\makeatother",
        r"\usepackage{card-deck}",
        rf"\renewcommand{{\cdDeckName}}{{{latex_escape(project['deck_name'])}}}",
        *(rf"\newcommand{{ \deckParamFact{x} }}{{ {x} }}" + "\n" for x in ("Fact", "Sound", "Spot", "Where")),
        r"\begin{document}",
    ]
    for n, card in enumerate(cards, 1):
        by: dict[str, list[str]] = {}
        for line in card["one_liners"]:
            by.setdefault(line["label"], []).append(latex_escape(line["text"]))
        out += [
            f"% Card: {card['name']}",
            f"%   id: {card['id']}",
            r"    \begin{cdCard}",
            r"        \begin{cdCardFront}",
            rf"            \cdCardImage{{ {image(n, card)} }}",
            r"        \end{cdCardFront}",
            r"        \begin{cdCardBack}",
            rf"            \cdName{{ {latex_escape(card_title(card['name']))} }}",
            r"            \vspace*{1mm}",
            *(rf"            \cdLeadFact{{ {t} }}" for t in by["fact"]),
            *(
                rf"            \cdLabelledSlot{{ \deckParamFact{x.capitalize()} }}{{ {' '.join(by[x])} }}"
                for x in ("sound", "spot", "where")
            ),
            r"        \end{cdCardBack}",
            r"    \end{cdCard}",
        ]
    return "\n".join([*out, r"\end{document}", ""])


def deck() -> str:
    project = tomllib.loads((HERE / "project.toml").read_text(encoding="utf-8"))
    return render(project, tomllib.loads((HERE / "cards.toml").read_text(encoding="utf-8"))["cards"])
