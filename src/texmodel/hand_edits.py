"""Hand edits read from the calls a document writes: `Plan.edits` sees text, this sees the arguments of the calls of the
packages' commands and environments (`_internal.calls`, by each component's signature) and the typed value each now
holds. No TeX runs, so a call a macro makes (one written inside a definition) is not read."""

import dataclasses
import difflib
import pathlib
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from itertools import accumulate, zip_longest

from ._internal.calls import MADE_BY_MACRO, ParsedCall, Unreadable, parse_calls
from .body import RefKind
from .components import Command, Environment, control_name
from .errors import TexmodelError
from .package import Package
from .plan import BEGIN_DOCUMENT, Edit, EditKind, FieldEdit, Line, Plan
from .std.tabularray import Longtblr, TableRow, Talltblr, Tblr
from .testing import Call, Component, read_call

type _Parsed = ParsedCall | Unreadable

# The tables of the package itself: a table's begin line is a call too, so an edit of it names its argument.
_TABLES = (Tblr, Longtblr, Talltblr)


def _key(call: Call | Unreadable) -> tuple[RefKind, str, tuple[str, ...] | None]:
    return (RefKind.CALL, call.name, None) if isinstance(call, Unreadable) else (call.kind, call.name, call.args)


def _changed(line: Line, old: Call, new: Call, classes: Mapping[str, Component]) -> Edit | None:
    """The edit from `old` to `new`, or None when they hold the same values (`.5` for `0.5`)."""
    if (old.kind, old.name) != (new.kind, new.name):
        return Edit(line.path, line.tex, new.probe_value(), EditKind.CHANGED)  # another command: the line says what
    fields: list[FieldEdit] = []
    for was, now in zip(read_call(classes[old.name], old), read_call(classes[new.name], new), strict=True):
        if was.found == now.found:
            continue
        if now.violation:
            now = dataclasses.replace(now, violation=dataclasses.replace(now.violation, path=f"{line.path}.{now.arg}"))
        elif now.value is not None and now.value == was.value:
            continue
        fields.append(now)
    return Edit(line.path, line.tex, new.probe_value(), EditKind.CHANGED, tuple(fields)) if fields else None


type _Probed = list[tuple[Edit, tuple[RefKind, str]]]  # an edit and the kind and name of the call it is about


def _probed(
    base: list[Call], got: list[_Parsed], plan: Plan, at: list[int], classes: Mapping[str, Component]
) -> _Probed:
    """What the calls say changed: `at` are the indices of the plan lines of `base`, one each."""
    probed: _Probed = []
    calls = [c.call if isinstance(c, ParsedCall) else c for c in got]
    ops = difflib.SequenceMatcher(None, [_key(c) for c in base], [_key(c) for c in calls], autojunk=False).get_opcodes()
    for tag, a1, a2, b1, b2 in ops:
        if tag == "equal":
            continue
        for k, (old, new) in enumerate(zip_longest(base[a1:a2], calls[b1:b2])):
            line = plan.lines[at[a1 + k]] if old else None
            if line and old and isinstance(new, Call):
                edit = _changed(line, old, new, classes)
            elif line and old and new:  # its call cannot be read
                edit = Edit(line.path, line.tex, "", EditKind.UNREAD)
            elif line:
                edit = Edit(line.path, line.tex, "", EditKind.REMOVED)
            elif isinstance(new, Unreadable):
                continue  # its line says it was added
            else:
                assert new is not None
                edit = Edit(plan.lines[at[a1 - 1]].path if a1 else "document", "", new.probe_value(), EditKind.ADDED)
            if edit and (call := old or new):
                follows = at[a1 - 1] + 1 if a1 else plan.lines.index(BEGIN_DOCUMENT) + 1
                edit = dataclasses.replace(edit, plan_line=at[a1 + k] + 1 if old else follows)
                probed.append((edit, (call.kind if isinstance(call, Call) else RefKind.CALL, call.name)))
    return probed


def _leading(text: str, classes: Mapping[str, Component]) -> tuple[RefKind, str] | None:
    """The kind and name of the call a line starts with (after its indentation), if it starts with one."""
    first = next(iter(parse_calls(text, classes)), None)
    if first is None or text[: first.start].strip():
        return None
    return (first.call.kind, first.call.name) if isinstance(first, ParsedCall) else (RefKind.CALL, first.name)


def _merged(line_edits: list[Edit], probed: _Probed, classes: Mapping[str, Component]) -> list[Edit]:
    """The line edits, each with what the calls add. A `CHANGED` line takes the fields of the probe's edit at its
    path, is `REMOVED` when the probe lost its call (`% \\acFact{...}`), or is `UNREAD` (its call cannot be read, or
    reads as the plan's). An added or removed line stays as it is and uses up one probe edit about the same call
    (equal neighbouring calls cannot be told apart, so the two diffs may name different ones). What is left only the
    calls showed."""
    out: list[Edit] = []

    def pop(path: str, kind: EditKind) -> Edit | None:
        i = next((i for i, (p, _) in enumerate(probed) if (p.path, p.kind) == (path, kind)), None)
        return None if i is None else probed.pop(i)[0]

    for e in line_edits:
        if e.kind is EditKind.CHANGED:
            if probe := pop(e.path, EditKind.CHANGED):
                out.append(dataclasses.replace(e, fields=probe.fields))
            elif pop(e.path, EditKind.REMOVED):  # its call is no longer run: commented out, the line still there
                out.append(dataclasses.replace(e, kind=EditKind.REMOVED, fields=()))
            else:
                pop(e.path, EditKind.UNREAD)
                out.append(dataclasses.replace(e, kind=EditKind.UNREAD, fields=()))
            continue
        out.append(e)
        if who := _leading(e.expected or e.found, classes):
            i = next((i for i, (p, w) in enumerate(probed) if p.kind is e.kind and w == who), None)
            if i is not None:
                probed.pop(i)
    return [*out, *(p for p, _ in probed)]


def _classes(packages: tuple[Package, ...], stub: Sequence[Component]) -> dict[str, Component]:
    classes = {control_name(c): c for p in packages for c in p.registered if issubclass(c, Command | Environment)}
    if any(issubclass(c, TableRow) for c in classes.values()):
        stub = [*stub, *_TABLES]
    classes |= {control_name(c): c for c in stub}
    if not classes:
        raise TexmodelError(
            "no command or environment to read", code="TM-X033", hint="pass the packages the document loads"
        )
    return classes


def _lines_of(plan: Plan, calls: Sequence[_Parsed]) -> list[int]:
    """The index of the plan line each of the plan's own calls stands on, in order."""
    starts = list(accumulate((len(x.tex) + 1 for x in plan.lines), initial=0))
    return [bisect_right(starts, c.start) - 1 for c in calls if isinstance(c, ParsedCall)]


def read_edits(
    plan: Plan,
    text: str,
    *packages: Package,
    file: pathlib.Path | None = None,
    stub: Sequence[Component] = (),
) -> list[Edit]:
    """What `text` changed against `plan`: `Plan.edits` with each `CHANGED` line's `fields` carrying the typed value the
    argument now holds (or the `Violation` saying it holds none), a line that differs but whose call reads as the plan's
    own (or cannot be read) as `UNREAD` (a comment, spacing, an extra argument), and a call commented out or in dead
    text (`\\iffalse`) as `REMOVED`.

    `packages` are the ones the document loads: every command and environment of them is read; `file` is the file `text`
    was read from, which every edit carries. `stub` are components of other packages to read too. `tblr`, `longtblr`
    and `talltblr` are read whenever a `TableRow` is. The calls are the ones written: a call inside a definition is one
    a macro makes, so it is `UNREAD` in `text` and `TM-X035` in the plan (`known-limitations.md`)."""
    classes = _classes(packages, stub)
    made = parse_calls(plan.text, classes)
    if macro := next((p for p in made if isinstance(p, Unreadable) and p.why == MADE_BY_MACRO), None):
        raise TexmodelError(
            f"line {plan.text.count(chr(10), 0, macro.start) + 1} of the plan calls \\{macro.name} inside a definition",
            code="TM-X035",
            hint="a macro of the hand-written TeX in the plan makes a call that is not read; write the call in place",
        )
    base = [p.call for p in made if isinstance(p, ParsedCall)]
    got = list(parse_calls(text, classes))
    probed = _probed(base, got, plan, _lines_of(plan, made), classes)
    return [dataclasses.replace(e, file=file) for e in _merged(plan.edits(text), probed, classes)]


__all__ = ["read_edits"]
