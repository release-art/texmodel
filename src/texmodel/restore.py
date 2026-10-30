"""Restore the data behind a hand-edited document (§21): from the document texmodel last wrote and the edits found
in the file, the document that writes those edits, and every edit it cannot restore with its reason.

```py
restored = restore(pkg, document, pkg.plan(document).edits(text))
restored.document    # the document with every applied edit
restored.applied     # the edits it holds
restored.unapplied   # Unapplied(edit, reason, violation, writes) for each one it does not
```

An edit is applied only when the restored data writes it: rendering the document with that edit alone gives the edited
line, or no line for a removal. Nothing starts a process; an argument's text is read by its field's type.
"""

import dataclasses
import enum
import pathlib
import typing
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from ._internal.read import detokenized, read_field
from ._internal.values import value_ok
from .body import Comment
from .components import Command, Environment, Node
from .document import Document
from .errors import DeclarationError, Violation
from .plan import BEGIN_DOCUMENT, Edit, EditKind, Plan, data_path

if TYPE_CHECKING:
    from .package import Package


@enum.unique
class Reason(enum.StrEnum):
    """Why an edit is not restored. The one registry of these codes: a test refuses a `TM-R` code anywhere else."""

    NO_DATA_CHANGE = "TM-R001"  # TeX reads the same calls (`UNREAD`): nothing to ingest
    NOT_DATA = "TM-R002"  # a line no node wrote: the header, the class and package lines, the preamble
    SETTING = "TM-R003"  # a setting's line: settings are not restored
    COMMENT = "TM-R004"  # a `Comment`'s line (a card's id): never restored
    ADDED_LINE = "TM-R005"  # a line the document did not have
    NOT_IN_ARGUMENT = "TM-R006"  # the change is over a command name, a delimiter or several lines, or no argument
    PARTIAL_REMOVAL = "TM-R007"  # part of a node removed or commented out, or a commented line also edited
    INVALID_VALUE = "TM-R008"  # an argument that reads to no value of its field: `violation` says why
    UNREADABLE = "TM-R009"  # a field whose type is not read back from text (a colour, a key list)
    GRAMMAR = "TM-R010"  # a removal the parent's grammar refuses: `violation` is its rule
    MISMATCH = "TM-R011"  # the restored data writes another line: `writes` is that line


@dataclasses.dataclass(frozen=True)
class Unapplied:
    edit: Edit
    reason: Reason
    violation: Violation | None = None  # what the check below said: `TM-C021`, the grammar's rule
    writes: str | None = None  # for `MISMATCH`: the line the restored data writes instead
    # for `ADDED_LINE`: the plan path of the node the line stands in (`""`: the document) and of the child it follows
    # (`None`: it is the first); both `None` for a line outside the content
    parent: str | None = None
    after: str | None = None


@dataclasses.dataclass(frozen=True)
class Restored:
    document: Document
    applied: tuple[Edit, ...]
    unapplied: tuple[Unapplied, ...]


@dataclasses.dataclass(frozen=True)
class _Change:
    """One node changed (`update`: its new fields) or removed (`update` None), and the edits that make it."""

    path: str
    lines: tuple[int, ...]  # the plan lines it covers
    edits: tuple[int, ...]  # indices into the edits given
    update: Mapping[str, object] | None


def _node_at(document: Document, where: pathlib.PurePosixPath | None) -> Node | None:
    """The node at a data path, or `None` for a line no node wrote."""
    if where is None or where.parts[1:2] != ("content",):
        return None
    node: Node | None = None
    nodes = document.content
    for index in where.parts[2::2]:
        node = nodes[int(index)]
        nodes = node.content if isinstance(node, Environment) else ()
    return node


def _lines_of(plan: Plan, edits: Sequence[Edit]) -> list[int | None]:
    """The plan line each edit stands for, by its `plan_line` (`None` for an added line), or a refusal of an edit that
    is not of this plan: its line is not there, or holds another path or text."""
    out: list[int | None] = []
    for edit in edits:
        n = edit.plan_line
        line = plan.lines[n - 1] if n is not None and 0 < n <= len(plan.lines) else None
        if edit.kind is EditKind.ADDED:
            ok = n == 0 or (line is not None and line.path == edit.path)
        else:
            ok = line is not None and (line.path, line.tex) == (edit.path, edit.expected)
        if not ok:
            raise DeclarationError(
                f"{edit.path}: {edit.expected or edit.found!r} is not a line of this document's plan",
                code="TM-X034",
                path=edit.path,
                hint="restore the edits found against this document's plan (`plan.edits`, `read_edits`)",
            )
        out.append(None if edit.kind is EditKind.ADDED or n is None else n - 1)
    return out


def _placed(document: Document, plan: Plan, follows: int) -> tuple[str | None, str | None]:
    """Where a line added after plan line `follows` (1-based) stands among the nodes: its parent (`""`, the document)
    and the child it follows (`None`: first). `(None, None)` outside the content: the header, the preamble."""
    before = plan.lines[follows - 1] if follows else None
    if before is None or before.path == "document":
        return ("", None) if before == BEGIN_DOCUMENT else (None, None)
    node = _node_at(document, data_path(before.path))
    if node is None:
        return None, None
    first = next(i for i, x in enumerate(plan.lines) if x.path == before.path)
    if isinstance(node, Environment) and follows - 1 == first:  # right after its \\begin: its first child
        return before.path, None
    return before.path.rpartition("/")[0], before.path


def _commented_out(edit: Edit) -> bool:
    """The line turned into a comment of itself: `%`, optional spaces, the line unchanged (leading spaces aside)."""
    found = edit.found.lstrip()
    return found.startswith("%") and found[1:].lstrip() == edit.expected.lstrip() != ""


def _update(node: "Command | Environment", edit: Edit) -> Mapping[str, object] | Unapplied:
    """The fields a changed call gives its node, each argument read by its field's type."""
    args = {a.name: a for a in type(node).__tm_args__}
    update: dict[str, object] = {}
    for found in edit.fields:
        a = args[found.arg]
        if found.violation is not None:
            return Unapplied(edit, Reason.INVALID_VALUE, found.violation)
        if a.optional and not a.token and not found.found:  # left out: the field's default
            update[a.name] = type(node).model_fields[a.name].get_default(call_default_factory=True)
            continue
        read = read_field(a, detokenized(found.found))
        if read.violation is not None:
            return Unapplied(edit, Reason.INVALID_VALUE, read.violation)
        if read.value is None or not value_ok(a.body, read.value):  # a colour's parts read, but not its model
            return Unapplied(edit, Reason.UNREADABLE)
        update[a.name] = read.value
    return update


def _rebuilt(
    nodes: Sequence[Node], prefix: str, changes: Mapping[str, Mapping[str, object] | None]
) -> tuple[Node, ...]:
    """`nodes` (whose paths start with `prefix`) with each change at its path."""
    out: list[Node] = []
    for i, node in enumerate(nodes):
        path = f"{prefix}{type(node).__name__}[{i}]"
        if path in changes and changes[path] is None:
            continue
        if update := changes.get(path):
            node = typing.cast("Environment", node).model_copy(update=dict(update))
        if isinstance(node, Environment) and any(p.startswith(path + "/") for p in changes):
            node = node.model_copy(update={"content": _rebuilt(node.content, path + "/", changes)})
        out.append(node)
    return tuple(out)


def _with(document: Document, changes: Sequence[_Change]) -> Document:
    rebuilt = _rebuilt(document.content, "", {c.path: c.update for c in changes})
    return Document(*rebuilt, options=document.options, settings=document.settings, preamble=document.preamble)


def _checked(
    pkg: "Package", document: Document, base: Plan, edits: Sequence[Edit], change: _Change
) -> Unapplied | None:
    """Why `change` alone does not write what its edits found, or `None`: the grammar holds and the plan of the
    document with it is the plan's text with those lines edited (or gone)."""
    # ponytail: one plan of the whole document per change, so edits x document size; a deck is small. Render only the
    # changed node's lines if a large document with many edits is slow.
    alone = _with(document, [change])
    edit = edits[change.edits[0]]
    if problems := [v for node in alone.content for v in node.violations()]:
        return Unapplied(edit, Reason.GRAMMAR if change.update is None else Reason.INVALID_VALUE, problems[0])
    found = {i: edits[k].found for i, k in zip(change.lines, change.edits, strict=True)}
    want = [found.get(i, line.tex) for i, line in enumerate(base.lines) if change.update is not None or i not in found]
    written = [line.tex for line in pkg.plan(alone).lines]
    if written != want:
        return Unapplied(edit, Reason.MISMATCH, writes=written[change.lines[0]])
    return None


def _reason(edit: Edit, line: int | None, node: Node | None) -> Reason | None:
    """Why an edit is not data to restore, or `None` for a removal or a changed call."""
    if edit.kind is EditKind.UNREAD:
        return Reason.NO_DATA_CHANGE
    if line is None:
        return Reason.ADDED_LINE
    if node is None:
        return Reason.SETTING if edit.path.startswith("settings[") else Reason.NOT_DATA
    if edit.kind is EditKind.REMOVED or _commented_out(edit):
        return None
    if isinstance(node, Comment):
        return Reason.COMMENT
    if edit.found.lstrip().startswith("%"):
        return Reason.PARTIAL_REMOVAL
    return None if edit.fields else Reason.NOT_IN_ARGUMENT


def _removals(
    document: Document, base: Plan, edits: Sequence[Edit], removed: Mapping[int, int]
) -> tuple[list[_Change], dict[int, Unapplied]]:
    """Each outermost node whose every line `removed` holds (plan line -> its edit), as a removal; the other removed
    lines, unapplied: part of a node, or a `Comment`, which is never restored."""
    changes: list[_Change] = []
    covered: set[int] = set()
    for path in dict.fromkeys(line.path for line in base.lines):  # outermost first: a node before its children
        lines = tuple(i for i, x in enumerate(base.lines) if x.path == path or x.path.startswith(path + "/"))
        node = _node_at(document, data_path(path))
        if node is not None and not isinstance(node, Comment) and set(lines) <= removed.keys() - covered:
            covered.update(lines)
            changes.append(_Change(path, lines, tuple(removed[i] for i in lines), None))
    unapplied: dict[int, Unapplied] = {}
    for i, k in removed.items():
        if i not in covered:
            comment = isinstance(_node_at(document, edits[k].data_path), Comment)
            unapplied[k] = Unapplied(edits[k], Reason.COMMENT if comment else Reason.PARTIAL_REMOVAL)
    return changes, unapplied


def restore(pkg: "Package", document: Document, edits: Sequence[Edit]) -> Restored:
    """The data `edits` restore into `document`, the one `pkg` last wrote; `edits` are `pkg.plan(document).edits(text)`
    or `texmodel.run.hand_edits.read_edits`'. Every edit comes back once, applied or unapplied, in the order given.
    A changed argument restores as its field's new value; a node's every line removed, or commented out as itself,
    restores as the node removed from its parent. Edits of another document's plan are refused (`TM-X034`)."""
    base = pkg.plan(document)
    outcome: dict[int, Unapplied] = {}
    removed: dict[int, int] = {}  # plan line -> the edit that removes it
    changes: list[_Change] = []
    for k, (edit, line) in enumerate(zip(edits, _lines_of(base, edits), strict=True)):
        node = _node_at(document, edit.data_path)
        if reason := _reason(edit, line, node):
            where = _placed(document, base, edit.plan_line or 0) if reason is Reason.ADDED_LINE else (None, None)
            outcome[k] = Unapplied(edit, reason, parent=where[0], after=where[1])
        elif edit.kind is EditKind.REMOVED or _commented_out(edit):
            removed[typing.cast("int", line)] = k
        elif isinstance(update := _update(typing.cast("Command | Environment", node), edit), Unapplied):
            outcome[k] = update
        else:
            changes.append(_Change(edit.path, (typing.cast("int", line),), (k,), update))
    removals, partial = _removals(document, base, edits, removed)
    outcome |= partial
    kept: list[_Change] = []
    for change in [*changes, *removals]:
        if failed := _checked(pkg, document, base, edits, change):
            outcome |= {k: dataclasses.replace(failed, edit=edits[k]) for k in change.edits}
        else:
            kept.append(change)
    applied = {k for change in kept for k in change.edits}
    return Restored(
        _with(document, kept),
        tuple(e for k, e in enumerate(edits) if k in applied),
        tuple(outcome[k] for k in range(len(edits)) if k in outcome),
    )


__all__ = ["Reason", "Restored", "Unapplied", "restore"]
