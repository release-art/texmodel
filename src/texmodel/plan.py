"""A document's plan (B2, D2): every output line with the path of what wrote it, so an edit to the file or a line of a
compile log names the component, not a line number.

`Package.plan(...)` returns it; `Plan.to_json()` is stored beside a committed document as its baseline, and
`Plan.edits(text)` compares a file with it by line, so a hand edit is found by path even when the model has moved on.
"""

import dataclasses
import difflib
import json
from collections.abc import Iterator

from .components import Environment, Node


@dataclasses.dataclass(frozen=True)
class Line:
    path: str  # "Card[1]/CardBack[1]/Name[0]", "preamble.after_package[2]", "header", "document"
    tex: str


@dataclasses.dataclass(frozen=True)
class Edit:
    """One difference: `expected` is empty for an added line, `found` for a removed one."""

    path: str
    expected: str
    found: str


def node_lines(node: Node, path: str) -> Iterator[Line]:
    """The lines a node renders; children are indexed within their parent, as `validate()` paths are."""
    rendered = node.render().splitlines()
    if not isinstance(node, Environment):
        yield from (Line(path, tex) for tex in rendered)
        return
    yield Line(path, rendered[0])
    for i, child in enumerate(node.content):
        yield from node_lines(child, f"{path}/{type(child).__name__}[{i}]")
    yield Line(path, rendered[-1])


@dataclasses.dataclass(frozen=True)
class Plan:
    lines: tuple[Line, ...]

    @property
    def text(self) -> str:
        return "\n".join(line.tex for line in self.lines) + "\n"

    def path_of(self, number: int) -> str:
        """The path that wrote line `number` (1-based, as TeX counts), e.g. from a log's `input line 39`."""
        return self.lines[number - 1].path

    def edits(self, text: str) -> list[Edit]:
        """What `text` changed against this plan; each difference carries the path of the line it replaced."""
        found = text.splitlines()
        out: list[Edit] = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [x.tex for x in self.lines], found).get_opcodes():
            if tag == "equal":
                continue
            for k in range(max(i2 - i1, j2 - j1)):
                was = self.lines[i1 + k] if i1 + k < i2 else None
                path = was.path if was else self.lines[i2 - 1].path  # an added line belongs to the line before it
                out.append(Edit(path, was.tex if was else "", found[j1 + k] if j1 + k < j2 else ""))
        return out

    def to_json(self) -> str:
        return json.dumps([[x.path, x.tex] for x in self.lines], ensure_ascii=False, indent=0) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "Plan":
        return cls(tuple(Line(path, tex) for path, tex in json.loads(text)))
