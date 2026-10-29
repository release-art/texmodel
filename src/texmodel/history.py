"""One model's history (§13, X5, X11): what stops stored data from being a valid tree of the current model, and what
changed between two of its JSON Schemas.

Releases, versions and running migrations are texpkg's; texpkg reads these to report what a migration has to place
(`problems`, `unplaced`) and to classify a release (`schema_changes`). A path is a data path, as JSON Pointer writes it
(`/content/1/content/0/text`).
"""

import dataclasses
import enum
import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

import pydantic

from .components import Command, Environment

_NODE = re.compile(r"([A-Z][A-Za-z]*)(?:\[(\d+)\])?")


@dataclasses.dataclass(frozen=True)
class Problem:
    """What stops the data from being a valid tree: where (`path`), why, the stored value, and the schema of the field
    there (`{}` when there is none)."""

    path: str
    reason: str
    value: object = None
    schema: Mapping[str, Any] = dataclasses.field(default_factory=dict[str, Any])


def pointer(loc: Sequence[str | int]) -> str:
    """The data path of a pydantic error location: a tagged child's class name follows its index and is not data."""
    out: list[str] = []
    after_index = False
    for part in loc:
        if after_index and isinstance(part, str):
            after_index = False
            continue
        after_index = isinstance(part, int)
        out.append(str(part))
    return "".join(f"/{part}" for part in out)


def violation_pointer(path: str) -> str:
    """The data path of a grammar violation's path (`Deck/Card[1]` is `/content/1`)."""
    parts = path.split("/")
    return "".join(f"/content/{m[2]}" for part in parts[1:] if (m := _NODE.fullmatch(part)) and m[2] is not None)


def schema_at(schema: Mapping[str, Any], loc: Sequence[str | int]) -> dict[str, Any]:
    """The schema of the field an error location names: `$defs[<class>].properties[<field>]`, `{}` if there is none."""
    classes = [str(p) for i, p in enumerate(loc) if isinstance(p, str) and i > 0 and isinstance(loc[i - 1], int)]
    owner = schema.get("$defs", {}).get(classes[-1]) if classes else schema
    field = loc[-1] if loc else None
    found = (owner or {}).get("properties", {}).get(field) if isinstance(field, str) and field != "content" else None
    return cast("dict[str, Any]", found) if isinstance(found, dict) else {}


def problems(
    model: type[Command] | type[Environment], data: Mapping[str, object], schema: Mapping[str, Any]
) -> list[Problem]:
    """Everything that stops `data` from being a valid tree of `model`: pydantic's errors with their constraint (from
    `schema`, the model's `json_schema`), then the grammar's violations."""
    try:
        tree = model.model_validate(data)
    except pydantic.ValidationError as exc:
        return [
            Problem(pointer(e["loc"]), e["msg"], e.get("input"), schema_at(schema, e["loc"]))
            for e in exc.errors(include_url=False)
        ]
    return [Problem(violation_pointer(v.path), v.message) for v in tree.violations()]


def unplaced(state: Mapping[str, Any], schema: Mapping[str, Any], path: str = "") -> list[Problem]:
    """The fields of stored data that the model has no field for, which loading it would drop without a word: a
    migration places each one or removes it on purpose. A node whose class the schema does not know is left to the
    validation, which names it. `$defaults` (texpkg's record of the values still at their default) is not a field."""
    fields = {schema.get("title"): schema.get("properties", {})} | {
        name: node.get("properties", {}) for name, node in schema.get("$defs", {}).items()
    }
    known = fields.get(state.get("type"))
    if known is None:
        return []
    out = [
        Problem(
            f"{path}/{key}",
            f"the model has no field {key!r}: a migration has to place it or remove it on purpose",
            value,
        )
        for key, value in state.items()
        if key not in known and key != "$defaults"
    ]
    for i, child in enumerate(state.get("content", ())):
        out += unplaced(child, schema, f"{path}/content/{i}")
    return out


@enum.unique
class Level(enum.IntEnum):
    """How much a change asks of the data's readers and writers; the largest of a release's changes decides its bump."""

    NONE = 0
    REVISION = 1  # a description, a default, a title: what the data means is unchanged
    COMPATIBLE = 2  # an addition: old data still validates
    BREAKING = 3


@dataclasses.dataclass(frozen=True)
class Change:
    level: Level
    where: str  # `Class.field`, `Class`
    what: str


_UPPER = ("maxLength", "maximum", "maxItems", "exclusiveMaximum")  # lowering one tightens it
_LOWER = ("minLength", "minimum", "minItems", "exclusiveMinimum")  # raising one tightens it


def _compare_property(where: str, old: dict[str, Any], new: dict[str, Any]) -> list[Change]:
    out: list[Change] = []
    for key in ("type", "$ref", "const", "format", "pattern"):
        if old.get(key) != new.get(key):
            out.append(Change(Level.BREAKING, where, f"{key} changed from {old.get(key)!r} to {new.get(key)!r}"))
    if (gone := [v for v in old.get("enum", ()) if v not in new.get("enum", ())]) or ("enum" in old) != ("enum" in new):
        out.append(Change(Level.BREAKING, where, f"values no longer allowed: {gone or 'any'}"))
    elif added := [v for v in new.get("enum", ()) if v not in old.get("enum", ())]:
        out.append(Change(Level.COMPATIBLE, where, f"values added: {added}"))
    for key in _UPPER + _LOWER:
        was, now = old.get(key), new.get(key)
        if was == now:
            continue
        tighter = now is not None and (was is None or (now < was if key in _UPPER else now > was))
        out.append(Change(Level.BREAKING if tighter else Level.COMPATIBLE, where, f"{key} {was} -> {now}"))
    if old.get("items") != new.get("items") and "items" in old:
        out += _compare_items(where, old["items"], new.get("items", {}))
    out += _compare_inline(where, old.get("properties", {}), new.get("properties", {}))
    for key in ("default", "description", "title"):
        if old.get(key) != new.get(key):
            out.append(Change(Level.REVISION, where, f"{key} changed"))
    return out


def _compare_inline(where: str, before: dict[str, Any], after: dict[str, Any]) -> list[Change]:
    """The properties of an object written inline in a property, not as a class of its own."""
    out: list[Change] = []
    for name in before:
        if name in after:
            out += _compare_property(f"{where}.{name}", before[name], after[name])
        else:
            out.append(Change(Level.BREAKING, f"{where}.{name}", "removed"))
    return out + [Change(Level.COMPATIBLE, f"{where}.{name}", "added") for name in sorted(after.keys() - before.keys())]


def _compare_items(where: str, old: dict[str, Any], new: dict[str, Any]) -> list[Change]:
    """The element schema of a list: a branch of a union that went is breaking, one that came is compatible."""

    def refs(items: dict[str, Any]) -> set[str]:
        branches = items.get("oneOf") or [items]
        return {b.get("$ref", b.get("type", "")) for b in branches}

    gone, added = refs(old) - refs(new), refs(new) - refs(old)
    out = [Change(Level.BREAKING, where, f"{g} is no longer allowed here") for g in sorted(gone)]
    out += [Change(Level.COMPATIBLE, where, f"{a} is allowed here") for a in sorted(added)]
    return out or ([] if old == new else _compare_property(where, old, new))


def _classes(schema: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out = {str(schema.get("title")): dict(schema)}
    out |= {str(node.get("title", name)): node for name, node in schema.get("$defs", {}).items()}
    return out


def schema_changes(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[Change]:
    """What changed in the data one model accepts, between two of its JSON Schemas, each change with its level, by
    Avro-style rules: an optional field or a value added, or a bound relaxed, is compatible; a class or a field removed,
    a field renamed without `renamed_from`, a bound tightened, a type changed or a field made required is breaking."""
    out: list[Change] = []
    was, now = _classes(old), _classes(new)
    for title in sorted(was.keys() - now.keys()):
        out.append(Change(Level.BREAKING, title, "no longer part of the model"))
    for title in sorted(now.keys() - was.keys()):
        out.append(Change(Level.COMPATIBLE, title, "added to the model"))
    for title in sorted(was.keys() & now.keys()):
        before, after = was[title].get("properties", {}), now[title].get("properties", {})
        renamed = {p.get("x-renamed-from"): name for name, p in after.items() if p.get("x-renamed-from")}
        for name in before:
            if name in after:
                out += _compare_property(f"{title}.{name}", before[name], after[name])
            elif name in renamed:
                out.append(
                    Change(Level.COMPATIBLE, f"{title}.{name}", f"renamed {renamed[name]} (old name still read)")
                )
            else:
                out.append(Change(Level.BREAKING, f"{title}.{name}", "removed"))
        now_required, was_required = set(now[title].get("required", ())), set(was[title].get("required", ()))
        for name in sorted((now_required - was_required) & before.keys() & after.keys()):
            out.append(Change(Level.BREAKING, f"{title}.{name}", "became required"))
        for name in sorted(after.keys() - before.keys() - set(renamed.values())):
            level = Level.BREAKING if name in now_required else Level.COMPATIBLE
            out.append(Change(level, f"{title}.{name}", "added" + (" and required" if name in now_required else "")))
    return out


def worst(changes: Sequence[Change]) -> Level:
    """The largest level of `changes`; `NONE` for none."""
    return max((c.level for c in changes), default=Level.NONE)


__all__ = [
    "Change",
    "Level",
    "Problem",
    "pointer",
    "problems",
    "schema_at",
    "schema_changes",
    "unplaced",
    "violation_pointer",
    "worst",
]
