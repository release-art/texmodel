"""A document's plan (B2, D2): every output line with the path of what wrote it, so an edit to the file or a line of a
compile log names the component, not a line number.

`Package.plan(...)` returns it; `Plan.to_json()` is stored beside a committed document as its baseline, and
`Plan.edits(text)` compares a file with it by line, so a hand edit is found by path even when the model has moved on.
"""

import dataclasses
import difflib
import enum
import json

from .errors import Violation


@dataclasses.dataclass(frozen=True)
class Span:
    """Where the text of one argument stands in a line: `line.tex[start:end]`, its delimiters excluded."""

    arg: str  # the field's name
    start: int
    end: int


@dataclasses.dataclass(frozen=True)
class Line:
    path: str  # "Card[1]/CardBack[1]/Name[0]", "preamble.after_package[2]", "header", "document"
    tex: str
    spans: tuple[Span, ...] = ()  # a command's call or an environment's begin line; empty for any other line


@enum.unique
class EditKind(enum.Enum):
    ADDED = "added"  # in the file, not in the plan
    REMOVED = "removed"  # in the plan, not in the file
    CHANGED = "changed"
    UNREAD = "unread"  # the line differs, but TeX reads the same calls from it (`texmodel_build.hand_edits`)


@dataclasses.dataclass(frozen=True)
class FieldEdit:
    """One argument of an edited call. `found` is its text in the file; `value` the typed value it reads back to (None
    when it is not read or left out) and `violation` why it does not read, when it does not."""

    arg: str
    found: str
    value: object = None
    violation: Violation | None = None


@dataclasses.dataclass(frozen=True)
class Edit:
    """One difference. `kind` says which side lacks the line: a blank line has no text to tell by. `fields` are the
    arguments a `CHANGED` line changes, when every change lies inside one argument's text; else empty (the command
    name, a delimiter or a line without spans changed: the line text says what)."""

    path: str
    expected: str
    found: str
    kind: EditKind
    fields: tuple[FieldEdit, ...] = ()


def _found_at(equal: list[tuple[int, int, int]], at: int, *, first: bool, default: int) -> int:
    """The position in the found text of position `at` in the expected one, through the first (or last) unchanged run
    that reaches it, so text inserted right at an argument's edge falls inside the argument."""
    runs = [(i1, j1) for i1, i2, j1 in equal if i1 <= at <= i2]
    if not runs:
        return default
    i1, j1 = runs[0] if first else runs[-1]
    return j1 + at - i1


def _fields(line: Line, found: str) -> tuple[FieldEdit, ...]:
    """The arguments `found` changes, character by character against the line; empty unless every change lies inside the
    text of one argument."""
    if not line.spans:
        return ()
    ops = difflib.SequenceMatcher(None, line.tex, found, autojunk=False).get_opcodes()
    equal = [(i1, i2, j1) for tag, i1, i2, j1, _ in ops if tag == "equal"]
    hit: dict[Span, None] = {}  # in line order
    for tag, i1, i2, _, _ in ops:
        if tag == "equal":
            continue
        span = next((s for s in line.spans if s.start <= i1 and i2 <= s.end), None)
        if span is None:
            return ()
        hit[span] = None
    return tuple(
        FieldEdit(
            s.arg,
            found[
                _found_at(equal, s.start, first=True, default=0) : _found_at(
                    equal, s.end, first=False, default=len(found)
                )
            ],
        )
        for s in sorted(hit, key=lambda s: s.start)
    )


def _compared(line: str, ignore_comments: bool) -> str:
    """A comment line compares equal to any other comment line when comments are ignored."""
    return "%" if ignore_comments and line.lstrip().startswith("%") else line


@dataclasses.dataclass(frozen=True)
class Plan:
    lines: tuple[Line, ...]

    @property
    def text(self) -> str:
        return "\n".join(line.tex for line in self.lines) + "\n"

    def path_of(self, number: int) -> str:
        """The path that wrote line `number` (1-based, as TeX counts), e.g. from a log's `input line 39`."""
        return self.lines[number - 1].path

    def edits(self, text: str, *, ignore_comments: bool = False) -> list[Edit]:
        """What `text` changed against this plan; each difference carries the path of the line it replaced. With
        `ignore_comments`, a line that is a comment (starts with `%`) in both is not compared, so a changed audit block
        is no edit; a comment turned into text, or text into a comment, still is."""
        found = text.splitlines()
        out: list[Edit] = []
        a = [_compared(x.tex, ignore_comments) for x in self.lines]
        b = [_compared(x, ignore_comments) for x in found]
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
            if tag == "equal":
                continue
            for k in range(max(i2 - i1, j2 - j1)):
                was = self.lines[i1 + k] if i1 + k < i2 else None
                path = was.path if was else self.lines[i2 - 1].path  # an added line belongs to the line before it
                kind = EditKind.CHANGED if was and j1 + k < j2 else EditKind.REMOVED if was else EditKind.ADDED
                now = found[j1 + k] if j1 + k < j2 else ""
                fields = _fields(was, now) if was and kind is EditKind.CHANGED else ()
                out.append(Edit(path, was.tex if was else "", now, kind, fields))
        return out

    def to_json(self) -> str:
        rows = [
            [x.path, x.tex, [[s.arg, s.start, s.end] for s in x.spans]] if x.spans else [x.path, x.tex]
            for x in self.lines
        ]
        return json.dumps(rows, ensure_ascii=False, indent=0) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "Plan":
        return cls(
            tuple(
                Line(path, tex, tuple(Span(*s) for s in (spans[0] if spans else ())))
                for path, tex, *spans in json.loads(text)
            )
        )


__all__ = ["Edit", "EditKind", "FieldEdit", "Line", "Plan", "Span"]
