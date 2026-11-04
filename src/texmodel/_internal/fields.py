"""What a field says besides its type: the notes `field()` and `arg()` carry in a dataclass field's metadata."""

import dataclasses
from collections.abc import Mapping
from typing import Any

NOTES = "notes"
OPTIONS = "options"
KEYWORD = "keyword"


@dataclasses.dataclass(frozen=True)
class FieldNotes:
    """What `field()` and `arg()` say about a field besides its slot: its old name in data, its doc, its `x-` keys."""

    renamed_from: str | None = None
    doc: str | None = None
    meta: Mapping[str, object] = dataclasses.field(default_factory=dict[str, object])


def field_spec(default: object, notes: FieldNotes, options: object | None = None, *, keyword: bool = False) -> Any:  # noqa: ANN401  # as dataclasses.field
    """A dataclass field carrying `notes` (and `options`, an `ArgOptions`) in its metadata; the schema shows the doc,
    the old name as `x-renamed-from` and the meta as `x-` keys. `dataclasses.MISSING` makes it required. A `keyword`
    field stays keyword-only in a class whose required fields are positional."""
    metadata: dict[str, object] = {NOTES: notes, KEYWORD: keyword}
    if options is not None:
        metadata[OPTIONS] = options
    return dataclasses.field(default=default, metadata=metadata)  # pyright: ignore[reportArgumentType]
