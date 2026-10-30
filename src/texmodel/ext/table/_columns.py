"""Columns from a row model."""

import dataclasses
import types
import typing
from collections.abc import Sequence
from typing import Any

import pydantic

from ...components import AnyValue, Command, control_name, field
from ...errors import DeclarationError
from ...package import Package
from ...std import tabularray as t
from ...types import Length, Raw
from ..recorded import Recorded
from ._formats import NUMBERS, Format, Number, Text

# --- columns -------------------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Flex:
    """A column that takes the table's spare width, `n` parts of it (`tabularray`'s `X`)."""

    n: float = 1


@dataclasses.dataclass(frozen=True)
class Widest:
    """A column as wide as the widest cell of its kind in the whole document, tables included: each body cell (and the
    header label) records its width, and the column is that wide in the next run (`ext.recorded`). `declare` makes the
    recorded length `<Name>` and the command `Measure<Name>` that `tabularray`'s `cmd` applies to the cells; give it
    to `Col(width=)` in every table that shares the width. The first run sets the column to nothing, so rerun."""

    measure: type[Command]
    value: type[AnyValue]

    @classmethod
    def declare(cls, package: Package, name: str) -> "Widest":
        parts = Recorded(name).declare(package)
        record = rf"\{package.prefix}Record{name}"
        measure = package.make_command(
            f"Measure{name}",
            f"Set the text, recording its width as {name}.",
            fields={"text": (Raw, field())},
            body=rf"\setbox\z@\hbox{{#text}}{record}{{\the\wd\z@}}#text",
        )
        return cls(measure, parts.value)

    @property
    def length(self) -> Length:
        return Length.expr(rf"\{control_name(self.value)}")

    @property
    def cmd(self) -> Raw:
        return Raw(rf"\{control_name(self.measure)}")


@dataclasses.dataclass(frozen=True)
class Col:
    """How a field is a column. `label` defaults to the field's name; `group` is a header group, or nested groups outer
    first (`("2025", "H1")`): consecutive columns with the same group share a spanner. `unit` follows the label in
    brackets. `stub` marks the row-label column. `valign` is the vertical alignment (a block's default is the head of
    the row). `style` is a `ColumnSpec` for the whole column, `cells` a `CellSpec` for the body rows only: the header
    keeps its own look. Both are the `tabularray` escape hatch."""

    label: str | None = None
    _: dataclasses.KW_ONLY
    fmt: Format | None = None
    align: t.HAlign | None = None
    width: Length | Flex | Widest | None = None
    unit: str | None = None
    group: str | tuple[str, ...] | None = None
    stub: bool = False
    hide: bool = False
    valign: t.VAlign | None = None
    style: t.ColumnSpec | None = None
    cells: t.CellSpec | None = None


@dataclasses.dataclass(frozen=True)
class Column:
    name: str
    label: str
    fmt: Format
    align: t.HAlign
    valign: t.VAlign | None
    width: Length | Flex | Widest | None
    group: tuple[str, ...]
    stub: bool
    style: t.ColumnSpec | None
    cells: t.CellSpec | None


def _kinds(hint: Any) -> set[Any]:  # noqa: ANN401
    """The types of a field's annotation, without `None`: `float | None` is {float}."""
    found = typing.get_args(hint) if isinstance(hint, types.UnionType) else (hint,)
    return {m for m in found if m is not type(None)}


def _default_format(where: str, kinds: set[Any]) -> Format:  # noqa: ANN401
    if kinds in ({str}, {Raw}):
        return Text()
    if kinds == {int}:
        return Number(0)
    raise DeclarationError(
        f"{where}: no default format for {sorted(map(str, kinds))}",
        code="TM-M078",
        path=where,
        hint="give the column fmt=: Number, Percent, Money, Date, Label or Text",
    )


def _check_groups(model: type[pydantic.BaseModel], found: Sequence[Column]) -> None:
    for level in range(max(len(c.group) for c in found)):
        runs = [c.group[: level + 1] if len(c.group) > level else None for c in found]
        seen: set[tuple[str, ...]] = set()
        for before, run in zip([None, *runs], runs, strict=False):
            if run is None or run == before:
                continue
            if run in seen:
                raise DeclarationError(
                    f"{model.__name__}: group {'/'.join(run)} is not on consecutive columns",
                    code="TM-M079",
                    path=model.__name__,
                    hint="put the columns of a group next to each other",
                )
            seen.add(run)


def column_of(model: type[pydantic.BaseModel], name: str) -> Column | None:
    """The column of one field, or `None` when the field is hidden."""
    info = model.model_fields[name]
    where = f"{model.__name__}.{name}"
    node_rows = issubclass(model, t.TableRow)
    col = next((m for m in info.metadata if isinstance(m, Col)), Col())
    if col.hide:
        return None
    kinds = _kinds(info.annotation)
    if node_rows and col.fmt is not None:
        raise DeclarationError(
            f"{where}: the row command writes its cells, so a format has nothing to do",
            code="TM-M085",
            path=where,
            hint="drop fmt=, or build the table from a plain row model",
        )
    fmt = col.fmt or (Text() if node_rows else _default_format(where, kinds))
    if fmt.numeric and not kinds <= set(NUMBERS):
        raise DeclarationError(
            f"{where}: {type(fmt).__name__} formats numbers, the field is {sorted(map(str, kinds))}",
            code="TM-M078",
            path=where,
        )
    label = col.label if col.label is not None else name.replace("_", " ").capitalize()
    group = (col.group,) if isinstance(col.group, str) else col.group or ()
    shown = f"{label} ({col.unit})" if col.unit else label
    valign = col.valign or fmt.valign
    return Column(name, shown, fmt, col.align or fmt.align, valign, col.width, group, col.stub, col.style, col.cells)


def columns_of(model: object, group_by: str | None) -> tuple[Column, ...]:
    """The visible columns of a row model; a `group_by` field is a group label, not a column."""
    if not (isinstance(model, type) and issubclass(model, pydantic.BaseModel)):  # a caller may pass anything
        raise DeclarationError(f"Table: {model!r} is not a pydantic model", code="TM-M077")
    if group_by is not None and group_by not in model.model_fields:
        raise DeclarationError(
            f"Table: group_by {group_by!r} is not a field of {model.__name__}", code="TM-M081", path=model.__name__
        )
    found = [c for name in model.model_fields if name != group_by and (c := column_of(model, name)) is not None]
    if not found:
        raise DeclarationError(f"{model.__name__}: no visible column", code="TM-M077", path=model.__name__)
    if sum(c.stub for c in found) > 1:
        raise DeclarationError(f"{model.__name__}: more than one stub column", code="TM-M079", path=model.__name__)
    _check_groups(model, found)
    return tuple(found)
