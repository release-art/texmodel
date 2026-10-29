"""Hand edits read by TeX: each component of the packages is stubbed to log its call, the edited
file and the plan's own text are compiled, and the calls are compared. Where `Plan.edits` sees text, this sees what TeX
reads: the argument that changed and the typed value it now holds."""

import dataclasses
import difflib
import re
from collections.abc import Mapping, Sequence
from itertools import zip_longest

from texmodel.body import RefKind
from texmodel.components import Command, Environment, control_name
from texmodel.errors import TexmodelError
from texmodel.package import Package
from texmodel.plan import Edit, EditKind, FieldEdit, Line, Plan
from texmodel.testing import Call, Component, read_call, stub_tex

from .compiler import Compiler
from .testkit import run_probes


async def _calls(compiler: Compiler, tex: str, stubs: Sequence[Component], files: Mapping[str, str]) -> list[Call]:
    """The calls the stubs log when `tex` compiles, in document order."""
    stubbed = tex.replace(r"\begin{document}", stub_tex(stubs) + "\n" + r"\begin{document}", 1)
    found = await run_probes(compiler, stubbed, files)
    numbered = sorted((int(m.name.removeprefix("call")), m.value) for m in found if re.fullmatch(r"call\d+", m.name))
    return [Call.parse(value) for _, value in numbered]


def _key(call: Call) -> tuple[RefKind, str, tuple[str, ...]]:
    return call.kind, call.name, call.args


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


def _probed(base: list[Call], got: list[Call], lines: list[Line], classes: Mapping[str, Component]) -> _Probed:
    """What the calls say changed: `lines` are the plan lines of `base`, one each."""
    probed: _Probed = []
    ops = difflib.SequenceMatcher(None, [_key(c) for c in base], [_key(c) for c in got], autojunk=False).get_opcodes()
    for tag, a1, a2, b1, b2 in ops:
        if tag == "equal":
            continue
        for k, (old, new) in enumerate(zip_longest(base[a1:a2], got[b1:b2])):
            line = lines[a1 + k] if old else None
            if line and old and new:
                edit = _changed(line, old, new, classes)
            elif line:
                edit = Edit(line.path, line.tex, "", EditKind.REMOVED)
            else:
                assert new is not None
                edit = Edit(lines[a1 - 1].path if a1 else "document", "", new.probe_value(), EditKind.ADDED)
            if edit and (call := old or new):
                probed.append((edit, (call.kind, call.name)))
    return probed


def _merged(line_edits: list[Edit], probed: _Probed, is_call: re.Pattern[str]) -> list[Edit]:
    """The line edits, each with what the calls add. A `CHANGED` line takes the fields of the probe's edit at its
    path, is `REMOVED` when the probe lost its call (`% \\acFact{...}`), or is `UNREAD`. An added or removed line
    stays as it is and uses up one probe edit about the same call (equal neighbouring calls cannot be told apart, so
    the two diffs may name different ones). What is left only TeX saw."""
    out: list[Edit] = []
    for e in line_edits:
        if e.kind is EditKind.CHANGED:
            i = next((i for i, (p, _) in enumerate(probed) if (p.path, p.kind) == (e.path, e.kind)), None)
            gone = next((i for i, (p, _) in enumerate(probed) if (p.path, p.kind) == (e.path, EditKind.REMOVED)), None)
            if i is not None:
                out.append(dataclasses.replace(e, fields=probed.pop(i)[0].fields))
            elif gone is not None:  # its call TeX no longer runs: commented out, the line still there
                probed.pop(gone)
                out.append(dataclasses.replace(e, kind=EditKind.REMOVED, fields=()))
            else:
                out.append(dataclasses.replace(e, kind=EditKind.UNREAD, fields=()))
            continue
        out.append(e)
        if m := is_call.match(e.expected or e.found):
            who = (RefKind.OPEN if m[1] == "begin" else RefKind.CLOSE if m[1] else RefKind.CALL, m[2] or m[3])
            i = next((i for i, (p, w) in enumerate(probed) if p.kind is e.kind and w == who), None)
            if i is not None:
                probed.pop(i)
    return [*out, *(p for p, _ in probed)]


async def read_edits(
    compiler: Compiler, plan: Plan, text: str, *packages: Package, files: Mapping[str, str] | None = None
) -> list[Edit]:
    """What `text` changed against `plan`, read by TeX: `Plan.edits` with each `CHANGED` line's `fields` carrying the
    typed value the argument now holds (or the `Violation` saying it holds none), a line TeX reads as the plan's own
    as `UNREAD` (a comment, spacing, an extra argument, an unstubbed line), and the calls TeX makes or loses that the
    lines do not show (`\\iffalse`, `%`).

    `packages` are the ones the document loads: every command and environment of them is stubbed, and their generated
    `.sty` is written beside the document; `files` are others it loads (path -> text). The plan's own text is compiled
    too, as the baseline. A document that does not compile raises `CompileError`, so nothing is read from a broken one.
    A stubbed macro redefined in `text` is not noticed: its calls vanish."""
    classes = {control_name(c): c for p in packages for c in p.registered if issubclass(c, Command | Environment)}
    if not classes:
        raise TexmodelError(
            "no command or environment to stub", code="TM-X033", hint="pass the packages the document loads"
        )
    names = "|".join(sorted(map(re.escape, classes), key=len, reverse=True))
    is_call = re.compile(rf"\s*\\(?:(begin|end)\{{({names})\}}|({names})(?![A-Za-z@]))")
    lines = [x for x in plan.lines if is_call.match(x.tex)]
    sheets = {path: tex for p in packages for path, tex in p.files().items()} | dict(files or {})
    stubs = list(classes.values())
    base = await _calls(compiler, plan.text, stubs, sheets)
    if len(base) != len(lines):
        raise TexmodelError(
            f"the plan makes {len(base)} calls of stubbed components but {len(lines)} of its lines call one",
            code="TM-X032",
            hint="a macro of the hand-written TeX in the plan calls a component; give a `Package` it was written with",
        )
    probed = _probed(base, await _calls(compiler, text, stubs, sheets), lines, classes)
    return _merged(plan.edits(text), probed, is_call)


__all__ = ["read_edits"]
