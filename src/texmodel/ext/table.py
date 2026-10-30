r"""table: a table from a row model, set with `tabularray` and booktabs-style rules.

The row model is a pydantic model; its fields are the columns, in order, and `Col(...)` on a field says how the column
reads: its label, format, alignment, width, unit and header group. Cell text is always written by a format, which
escapes it, so no `&` or `\\` is written by hand. Numbers are formatted in Python, right-aligned at one number of
decimals per column, which puts the points in line.

```python
class Sale(BaseModel):
    region: Annotated[str, Col("Region")]
    q1: Annotated[float, Col("Q1", group="2025", fmt=Number(0))]
    q2: Annotated[float, Col("Q2", group="2025", fmt=Number(0))]

rows = [Sale(region="North", q1=1200, q2=1340)]
table = Table(Sale, rows, caption="Revenue", totals=[Total("Total", sum=("q1", "q2"))])
Document(table.node())          # a Tblr, Talltblr or Longtblr of texmodel.std.tabularray
```

A field of type `str` (`Text`), `Raw` or `int` has a default format; any other type needs `fmt=`. A table with a
caption or notes is a `Talltblr`; `long=True` makes a `Longtblr` that repeats its header on every page. `Look` is the
typography: rule weights, padding and the header font.
"""

import dataclasses
import decimal
import types
import typing
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from typing import Any, ClassVar, Final

import pydantic

from ..components import ColourRef, Passthrough
from ..errors import DeclarationError, ValidationError
from ..keyvals import Entry
from ..std import tabularray as t
from ..types import Length, Raw, escape

_NUMBERS: Final = (int, float, Decimal)
_SPACE: Final = r"\,"  # a thin space: the group separator of digits


# --- formats -------------------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Format:
    """How a value of a column is written: a pure function from value to escaped TeX. `missing` stands for `None`."""

    missing: str = dataclasses.field(default="\u2013", kw_only=True)
    align: ClassVar[t.HAlign] = t.HAlign.LEFT
    numeric: ClassVar[bool] = False

    def tex(self, value: object) -> str:
        return self.missing if value is None else self._tex(value)

    def _tex(self, value: object) -> str:
        raise NotImplementedError


@dataclasses.dataclass(frozen=True)
class Text(Format):
    """Text, escaped; a `Raw` passes as written. Line breaks and runs of spaces become one space."""

    def _tex(self, value: object) -> str:
        return value.tex if isinstance(value, Raw) else escape(" ".join(str(value).split()))


@dataclasses.dataclass(frozen=True)
class Number(Format):
    r"""A number at `decimals` places (rounded half up), digits grouped in threes from four digits (`thousands`), with
    `point` and `separator` as TeX (`Number(2, point="{,}")` is a decimal comma), a true minus, a plus with `sign`."""

    decimals: int = 0
    thousands: bool = True
    point: str = "."
    separator: str = _SPACE
    sign: bool = False
    minus: str = "−"
    align: ClassVar[t.HAlign] = t.HAlign.RIGHT
    numeric: ClassVar[bool] = True

    def __post_init__(self) -> None:
        if self.decimals < 0:
            raise DeclarationError(f"{type(self).__name__}: decimals {self.decimals} is not 0 or more", code="TM-M077")

    def _scaled(self, value: Decimal) -> Decimal:
        return value

    def _suffix(self) -> str:
        return ""

    def _tex(self, value: object) -> str:
        if isinstance(value, bool) or not isinstance(value, _NUMBERS):
            raise TypeError(f"{type(self).__name__}: {value!r} is not a number")
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError(f"{type(self).__name__}: {value!r} is not finite")
        number = self._scaled(number).quantize(Decimal(1).scaleb(-self.decimals), rounding=decimal.ROUND_HALF_UP)
        whole, _, fraction = f"{abs(number):f}".partition(".")
        if self.thousands and len(whole) > 3:
            groups = [whole[max(i - 3, 0) : i] for i in range(len(whole), 0, -3)]
            whole = self.separator.join(reversed(groups))
        text = whole + (self.point + fraction if fraction else "") + self._suffix()
        return (self.minus if number < 0 else "+" if self.sign and number > 0 else "") + text


@dataclasses.dataclass(frozen=True)
class Percent(Number):
    r"""A fraction as a percentage: `0.123` is `12.3 %` with `Percent(1)`."""

    def _scaled(self, value: Decimal) -> Decimal:
        return value * 100

    def _suffix(self) -> str:
        return r"\,\%"


# --- columns -------------------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Flex:
    """A column that takes the table's spare width, `n` parts of it (`tabularray`'s `X`)."""

    n: float = 1


@dataclasses.dataclass(frozen=True)
class Col:
    """How a field is a column. `label` defaults to the field's name; `group` is a header group, or nested groups outer
    first (`("2025", "H1")`): consecutive columns with the same group share a spanner. `unit` follows the label in
    brackets. `stub` marks the row-label column. `style` is a `ColumnSpec`, the `tabularray` escape hatch."""

    label: str | None = None
    _: dataclasses.KW_ONLY
    fmt: Format | None = None
    align: t.HAlign | None = None
    width: Length | Flex | None = None
    unit: str | None = None
    group: str | tuple[str, ...] | None = None
    stub: bool = False
    hide: bool = False
    style: t.ColumnSpec | None = None


@dataclasses.dataclass(frozen=True)
class _Column:
    name: str
    label: str
    fmt: Format
    align: t.HAlign
    width: Length | Flex | None
    group: tuple[str, ...]
    stub: bool
    style: t.ColumnSpec | None


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
        hint="give the column fmt=: Number(decimals), Percent(decimals) or Text()",
    )


def _check_groups(model: type[pydantic.BaseModel], found: Sequence[_Column]) -> None:
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


def _columns(model: object) -> tuple[_Column, ...]:  # `object`: a caller without a type checker may pass anything
    if not (isinstance(model, type) and issubclass(model, pydantic.BaseModel)):
        raise DeclarationError(f"Table: {model!r} is not a pydantic model", code="TM-M077")
    found: list[_Column] = []
    for name, info in model.model_fields.items():
        where = f"{model.__name__}.{name}"
        col = next((m for m in info.metadata if isinstance(m, Col)), Col())
        if col.hide:
            continue
        kinds = _kinds(info.annotation)
        fmt = col.fmt or _default_format(where, kinds)
        if fmt.numeric and not kinds <= set(_NUMBERS):
            raise DeclarationError(
                f"{where}: {type(fmt).__name__} formats numbers, the field is {sorted(map(str, kinds))}",
                code="TM-M078",
                path=where,
            )
        label = col.label if col.label is not None else name.replace("_", " ").capitalize()
        group = (col.group,) if isinstance(col.group, str) else col.group or ()
        found.append(
            _Column(
                name,
                f"{label} ({col.unit})" if col.unit else label,
                fmt,
                col.align or fmt.align,
                col.width,
                group,
                col.stub,
                col.style,
            )
        )
    if not found:
        raise DeclarationError(f"{model.__name__}: no visible column", code="TM-M077", path=model.__name__)
    if sum(c.stub for c in found) > 1:
        raise DeclarationError(f"{model.__name__}: more than one stub column", code="TM-M079", path=model.__name__)
    _check_groups(model, found)
    return tuple(found)


# --- the other parts -----------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Total:
    """A row of sums under the body, set apart by a rule: the label in the stub (or first) column, and the `sum` of each
    column named, in that column's format. Other cells are empty."""

    label: str
    sum: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class Note:
    """A paragraph under the table, headed by its `tag`: `Note: Provisional figures.`"""

    text: str
    tag: str = "Note"


@dataclasses.dataclass(frozen=True)
class Look:
    """The typography of a table. The default is booktabs': no vertical rules, a heavy rule above and below, a light one
    under the header, little padding at the edges, a bold header. `header_bg` and `header_fg` take a colour value."""

    heavy: Length = Length("0.08em")
    light: Length = Length("0.05em")
    rowsep: Length = Length("0.5ex")
    colsep: Length = Length("6pt")
    header_font: Raw | None = Raw(r"\bfseries")
    header_bg: ColourRef | None = None
    header_fg: ColourRef | None = None

    BOOKTABS: ClassVar["Look"]


Look.BOOKTABS = Look()


# --- the table -----------------------------------------------------------------------------------------------------


def _cell_text(column: _Column, value: object) -> str:
    return column.fmt.tex(value)


@dataclasses.dataclass(frozen=True)
class Table[T: pydantic.BaseModel]:
    """A row model and its rows, with the parts of a table. `rows` are instances of the model, or mappings it validates;
    `node()` is the `tabularray` environment, `render()` its TeX."""

    model: type[T]
    rows: Iterable[T | Mapping[str, Any]]
    _: dataclasses.KW_ONLY
    caption: str | None = None
    label: str | None = None
    totals: Sequence[Total] = ()
    notes: Sequence[Note] = ()
    look: Look = Look.BOOKTABS
    long: bool = False
    width: Length | None = None
    rules: Sequence[Entry] = ()
    columns: tuple[_Column, ...] = dataclasses.field(init=False, repr=False)
    data: tuple[T, ...] = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        columns = _columns(self.model)
        names = {c.name: c for c in columns}
        for total in self.totals:
            for name in total.sum:
                if name not in names or not names[name].fmt.numeric:
                    raise DeclarationError(
                        f"Total({total.label!r}): sum of {name!r}, which is not a visible number column",
                        code="TM-M080",
                        path=f"{self.model.__name__}.{name}",
                    )
        body: list[T] = []
        for i, row in enumerate(self.rows):
            if isinstance(row, self.model):
                body.append(row)
                continue
            try:
                body.append(self.model.model_validate(row))
            except pydantic.ValidationError as exc:
                raise ValidationError(f"row {i}: {exc}", code="TM-C026", path=f"rows[{i}]") from exc
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "data", tuple(body))

    # The header: one row per level of group, then the labels.
    def _header(self) -> tuple[list[str], list[Entry], list[Entry]]:
        """The header lines, the entries that span and style them, and the light rules under them."""
        levels = max(len(c.group) for c in self.columns)
        lines: list[str] = []
        entries: list[Entry] = []
        rules: list[Entry] = []
        for level in range(levels):
            cells = [""] * len(self.columns)
            start = 0
            while start < len(self.columns):
                path = self.columns[start].group[: level + 1]
                end = start
                while end + 1 < len(self.columns) and path and self.columns[end + 1].group[: level + 1] == path:
                    end += 1
                if len(self.columns[start].group) > level:
                    cells[start] = escape(path[-1])
                    if end > start:
                        entries.append(
                            t.cell(
                                level + 1,
                                start + 1,
                                t.CellSpec(halign=t.HAlign.CENTRE),
                                span=t.CellSpan(c=end - start + 1),
                            )
                        )
                    rules.append(
                        t.hline(
                            level + 2, t.HlineSpec(wd=self.look.light, lr=True, endpos=True), f"{start + 1}-{end + 1}"
                        )
                    )
                start = end + 1
            lines.append(_line(cells))
        lines.append(_line([escape(c.label) for c in self.columns]))
        return lines, entries, rules

    def _total(self, total: Total) -> list[str]:
        sums = {
            n: sum((Decimal(str(getattr(r, n))) for r in self.data if getattr(r, n) is not None), Decimal(0))
            for n in total.sum
        }
        lead = next((i for i, c in enumerate(self.columns) if c.stub), 0)
        return [
            escape(total.label) if i == lead else _cell_text(c, sums[c.name]) if c.name in sums else ""
            for i, c in enumerate(self.columns)
        ]

    def node(self) -> t.Tblr | t.Talltblr | t.Longtblr:
        """The table as a `tabularray` environment, typed down to its keys."""
        header, spans, under = self._header()
        h, n_body = len(header), len(self.data)
        lines = [*header, *(_line([_cell_text(c, getattr(r, c.name)) for c in self.columns]) for r in self.data)]
        look, last = self.look, len(self.columns)
        rules = [
            t.hline(1, t.HlineSpec(wd=look.heavy)),
            *under,
            t.hline(h + 1, t.HlineSpec(wd=look.light)),
            t.row(f"1-{h}", t.RowSpec(font=look.header_font, bg=look.header_bg, fg=look.header_fg)),
            t.column(1, t.ColumnSpec(leftsep=Length("0pt"))),
            t.column(last, t.ColumnSpec(rightsep=Length("0pt"))),
        ]
        for i, c in enumerate(self.columns, start=1):
            width = c.width
            rules.append(
                t.column(
                    i,
                    t.ColumnSpec(
                        halign=c.align,
                        wd=width if isinstance(width, Length) else None,
                        co=width.n if isinstance(width, Flex) else None,
                    ),
                )
            )
            if c.style is not None:
                rules.append(t.column(i, c.style))
        rules += spans  # after the columns': a cell's own alignment wins
        for k, total in enumerate(self.totals):
            row = h + n_body + k + 1
            lines.append(_line(self._total(total)))
            rules.append(t.row(row, t.RowSpec(font=look.header_font)))
            if k == 0:
                rules.append(t.hline(row, t.HlineSpec(wd=look.light)))
        rules.append(t.hline(t.selector("Z"), t.HlineSpec(wd=look.heavy)))
        inner = t.TblrInner(
            colspec=Raw("Q" * last),
            width=self.width,
            rowsep=look.rowsep,
            colsep=look.colsep,
            rowhead=h if self.long else None,
            rules=[*rules, *self.rules],
        )
        outer = t.TblrOuter(
            caption=self.caption,
            label=Raw(self.label) if self.label else None,
            rules=[t.remark(Raw(escape(n.tag)), Raw(escape(n.text))) for n in self.notes] or None,
        )
        env = t.Longtblr if self.long else t.Talltblr if self.caption or self.notes else t.Tblr
        content = Passthrough(Raw("\n".join(lines)))
        return env(content, outer=outer if self.caption or self.notes or self.label else None, inner=inner)

    def render(self) -> str:
        return self.node().render()


def _line(cells: list[str]) -> str:
    return " & ".join(cells) + r" \\"


__all__ = ["Col", "Flex", "Format", "Look", "Note", "Number", "Percent", "Table", "Text", "Total"]
