"""What a field says besides its type: the notes `field()` and `arg()` carry into pydantic's field metadata."""

import dataclasses
from collections.abc import Mapping
from typing import Any

import pydantic
from pydantic.fields import FieldInfo


@dataclasses.dataclass(frozen=True)
class FieldNotes:
    """What `field()` and `arg()` say about a field besides its slot: its old name in data, its doc, its `x-` keys."""

    renamed_from: str | None = None
    doc: str | None = None
    meta: Mapping[str, object] = dataclasses.field(default_factory=dict[str, object])


def field_info(default: object, notes: FieldNotes, *more: object, kw_only: bool | None) -> FieldInfo:
    """A pydantic field carrying `notes` (and `more`, an `ArgOptions`) in its metadata; the schema shows the doc, the
    old name as `x-renamed-from` and the meta as `x-` keys. `dataclasses.MISSING` makes it required."""
    extra: dict[str, Any] = {f"x-{k}": v for k, v in notes.meta.items()}
    if notes.renamed_from is not None:
        extra = {"x-renamed-from": notes.renamed_from, **extra}
    given: dict[str, Any] = {} if default is dataclasses.MISSING else {"default": default}
    info: FieldInfo = pydantic.Field(**given, kw_only=kw_only, description=notes.doc, json_schema_extra=extra or None)
    info.metadata += [notes, *more]
    return info
