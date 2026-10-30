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
typography: rule weights, padding and fonts. `group_by` sets runs of rows under group labels, `Highlight` styles rows
or cells by a predicate and `Span` merges cells across columns.
"""

import dataclasses
import datetime
import decimal
import enum
import itertools
import types
import typing
from collections.abc import Callable, Iterable, Mapping, Sequence
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

    missing: str = dataclasses.field(default="–", kw_only=True)
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

    def _prefix(self) -> str:
        return ""

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
        text = self._prefix() + whole + (self.point + fraction if fraction else "") + self._suffix()
        return (self.minus if number < 0 else "+" if self.sign and number > 0 else "") + text


@dataclasses.dataclass(frozen=True)
class Percent(Number):
    r"""A fraction as a percentage: `0.123` is `12.3 %` with `Percent(1)`."""

    def _scaled(self, value: Decimal) -> Decimal:
        return value * 100

    def _suffix(self) -> str:
        return r"\,\%"


@dataclasses.dataclass(frozen=True)
class Money(Number):
    r"""An amount with a currency `symbol` (TeX: `"€"`, `r"\$"`) before it, or after it with `after=True`."""

    decimals: int = 2
    symbol: str = dataclasses.field(default="", kw_only=True)
    after: bool = dataclasses.field(default=False, kw_only=True)

    def _prefix(self) -> str:
        return "" if self.after else self.symbol

    def _suffix(self) -> str:
        return f"{_SPACE}{self.symbol}" if self.after and self.symbol else ""


@dataclasses.dataclass(frozen=True)
class Date(Format):
    """A date or datetime by a `strftime` pattern (the portable directives; month and day names are English)."""

    pattern: str = "%Y-%m-%d"

    def _tex(self, value: object) -> str:
        if not isinstance(value, datetime.date):
            raise TypeError(f"Date: {value!r} is not a date")
        return escape(value.strftime(self.pattern))


@dataclasses.dataclass(frozen=True)
class Label(Format):
    """The text for each value, for an enum, a boolean or a code: `Label({True: "Yes", False: "No"})`. A value with no
    text is an error; a `Raw` text passes as written."""

    texts: Mapping[Any, str | Raw]

    def _tex(self, value: object) -> str:
        if value not in self.texts:
            raise ValueError(f"Label: no text for {value!r}")
        text = self.texts[value]
        return text.tex if isinstance(text, Raw) else escape(text)


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
        hint="give the column fmt=: Number, Percent, Money, Date, Label or Text",
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


def _column(model: type[pydantic.BaseModel], name: str) -> _Column | None:
    """The column of one field, or `None` when the field is hidden."""
    info = model.model_fields[name]
    where = f"{model.__name__}.{name}"
    col = next((m for m in info.metadata if isinstance(m, Col)), Col())
    if col.hide:
        return None
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
    shown = f"{label} ({col.unit})" if col.unit else label
    return _Column(name, shown, fmt, col.align or fmt.align, col.width, group, col.stub, col.style)


def _columns(model: object, group_by: str | None) -> tuple[_Column, ...]:
    """The visible columns of a row model; a `group_by` field is a group label, not a column."""
    if not (isinstance(model, type) and issubclass(model, pydantic.BaseModel)):  # a caller may pass anything
        raise DeclarationError(f"Table: {model!r} is not a pydantic model", code="TM-M077")
    if group_by is not None and group_by not in model.model_fields:
        raise DeclarationError(
            f"Table: group_by {group_by!r} is not a field of {model.__name__}", code="TM-M081", path=model.__name__
        )
    found = [c for name in model.model_fields if name != group_by and (c := _column(model, name)) is not None]
    if not found:
        raise DeclarationError(f"{model.__name__}: no visible column", code="TM-M077", path=model.__name__)
    if sum(c.stub for c in found) > 1:
        raise DeclarationError(f"{model.__name__}: more than one stub column", code="TM-M079", path=model.__name__)
    _check_groups(model, found)
    return tuple(found)


# --- the other parts -----------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Total:
    """A row of sums under the body (or under each row group), set apart by a rule: the label in the stub (or first)
    column, and the `sum` of each column named, in that column's format. Other cells are empty."""

    label: str
    sum: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class Note:
    """A paragraph under the table, headed by its `tag`: `Note: Provisional figures.`"""

    text: str
    tag: str = "Note"


@dataclasses.dataclass(frozen=True)
class Highlight[T]:
    """Style the rows where `where(row)` holds: the whole row, or only the cells of `columns`. `bold` is `\\bfseries`;
    `font` is any other font commands, after it. Colours take a colour value (`bg=Ink`)."""

    where: Callable[[T], bool]
    columns: tuple[str, ...] | None = None
    _: dataclasses.KW_ONLY
    bg: ColourRef | None = None
    fg: ColourRef | None = None
    bold: bool = False
    font: Raw | None = None


@dataclasses.dataclass(frozen=True)
class Span[T]:
    """The cell of `column` takes the `count` columns from it, in the rows where `where(row)` holds (all rows without
    it); the cells it covers are written empty."""

    column: str
    count: int = 2
    where: Callable[[T], bool] | None = None


@enum.unique
class Rules(enum.Enum):
    """Which rules a table has: booktabs' (horizontal only, by weight), a grid of light rules, or none."""

    BOOKTABS = "booktabs"
    GRID = "grid"
    NONE = "none"


@dataclasses.dataclass(frozen=True)
class Look:
    """The typography of a table. The default is booktabs': no vertical rules, a heavy rule above and below, a light one
    under the header, little padding at the edges, a bold header and totals. `header_bg` and `header_fg` take a colour
    value. A row group's label is `group_font`, set `group_gap` below the group before; its rows are indented."""

    rules: Rules = Rules.BOOKTABS
    heavy: Length = Length("0.08em")
    light: Length = Length("0.05em")
    rowsep: Length = Length("0.5ex")
    colsep: Length = Length("6pt")
    header_font: Raw | None = Raw(r"\bfseries")
    header_bg: ColourRef | None = None
    header_fg: ColourRef | None = None
    total_font: Raw | None = Raw(r"\bfseries")
    group_font: Raw | None = Raw(r"\itshape")
    group_gap: Length = Length("1ex")
    indent: Length = Length("1em")

    BOOKTABS: ClassVar["Look"]
    GRID: ClassVar["Look"]
    PLAIN: ClassVar["Look"]


Look.BOOKTABS = Look()
Look.GRID = Look(rules=Rules.GRID, rowsep=Length("2pt"))
Look.PLAIN = Look(rules=Rules.NONE)


# --- the table -----------------------------------------------------------------------------------------------------


@dataclasses.dataclass
class _Layout:
    """The lines of a table and the table row of the group labels, the rows of data and the subtotals."""

    lines: list[str]
    position: list[int] = dataclasses.field(default_factory=list[int])
    labels: list[int] = dataclasses.field(default_factory=list[int])
    indents: list[tuple[int, int]] = dataclasses.field(default_factory=list[tuple[int, int]])
    subtotals: list[int] = dataclasses.field(default_factory=list[int])


def _ranges(numbers: Sequence[int]) -> list[int | str]:
    """Row numbers as selector parts, runs as ranges: `[3, 4, 5, 9]` is `["3-5", 9]`."""
    out: list[int | str] = []
    for _, run in itertools.groupby(enumerate(sorted(numbers)), key=lambda p: p[1] - p[0]):
        first, *_, last = [n for _, n in run] * 2
        out.append(first if first == last else f"{first}-{last}")
    return out


def _font(bold: bool, font: Raw | None) -> Raw | None:
    return Raw((r"\bfseries" if bold else "") + (font.tex if font else "")) if bold or font else None


def _visible(columns: Iterable[str], index: Mapping[str, int], where: str) -> None:
    for name in columns:
        if name not in index:
            raise DeclarationError(f"{name!r} is not a visible column", code="TM-M082", path=f"{where}.{name}")


def _line(cells: list[str]) -> str:
    return " & ".join(cells) + r" \\"


@dataclasses.dataclass(frozen=True)
class Table[T: pydantic.BaseModel]:
    """A row model and its rows, with the parts of a table. `rows` are instances of the model, or mappings it validates;
    `node()` is the `tabularray` environment, `render()` its TeX. `group_by` names a field whose runs of equal values
    become row groups, each under a label row (the field is not a column), with a `subtotal` row if given."""

    model: type[T]
    rows: Iterable[T | Mapping[str, Any]]
    _: dataclasses.KW_ONLY
    caption: str | None = None
    label: str | None = None
    group_by: str | None = None
    subtotal: Total | None = None
    totals: Sequence[Total] = ()
    notes: Sequence[Note] = ()
    highlights: Sequence[Highlight[T]] = ()
    spans: Sequence[Span[T]] = ()
    look: Look = Look.BOOKTABS
    long: bool = False
    width: Length | None = None
    rules: Sequence[Entry] = ()
    columns: tuple[_Column, ...] = dataclasses.field(init=False, repr=False)
    data: tuple[T, ...] = dataclasses.field(init=False, repr=False)
    groups: tuple[tuple[object, tuple[T, ...]], ...] = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        columns = _columns(self.model, self.group_by)
        self._check(columns)
        body: list[T] = []
        for i, row in enumerate(self.rows):
            if isinstance(row, self.model):
                body.append(row)
                continue
            try:
                body.append(self.model.model_validate(row))
            except pydantic.ValidationError as exc:
                raise ValidationError(f"row {i}: {exc}", code="TM-C026", path=f"rows[{i}]") from exc
        group_by = self.group_by
        key: Callable[[T], object] = (lambda r: getattr(r, group_by)) if group_by else (lambda _: None)
        groups = tuple((k, tuple(members)) for k, members in itertools.groupby(body, key=key))
        if len({k for k, _ in groups}) < len(groups):
            raise DeclarationError(
                f"Table: the rows of a {group_by!r} group are not together",
                code="TM-M081",
                path=self.model.__name__,
                hint="order the rows so that equal values are next to each other",
            )
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "data", tuple(body))
        object.__setattr__(self, "groups", groups)

    def _check(self, columns: tuple[_Column, ...]) -> None:
        """The parts name columns that are there and fit."""
        index = {c.name: i for i, c in enumerate(columns)}
        where = self.model.__name__
        if self.subtotal is not None and self.group_by is None:
            raise DeclarationError("Table: a subtotal needs group_by", code="TM-M081", path=where)
        for total in [*self.totals, *([self.subtotal] if self.subtotal else [])]:
            for name in total.sum:
                if name not in index or not columns[index[name]].fmt.numeric:
                    raise DeclarationError(
                        f"Total({total.label!r}): sum of {name!r}, which is not a visible number column",
                        code="TM-M080",
                        path=f"{where}.{name}",
                    )
        for highlight in self.highlights:
            _visible(highlight.columns or (), index, where)
        for span in self.spans:
            _visible([span.column], index, where)
            if span.count < 2 or index[span.column] + span.count > len(columns):
                raise DeclarationError(
                    f"Span({span.column!r}, {span.count}): {span.count} columns do not fit from there",
                    code="TM-M082",
                    path=f"{where}.{span.column}",
                )

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
                        span = t.CellSpan(c=end - start + 1)
                        entries.append(t.cell(level + 1, start + 1, t.CellSpec(halign=t.HAlign.CENTRE), span=span))
                    under = t.HlineSpec(wd=self.look.light, lr=True, endpos=True)
                    rules.append(t.hline(level + 2, under, f"{start + 1}-{end + 1}"))
                start = end + 1
            lines.append(_line(cells))
        lines.append(_line([escape(c.label) for c in self.columns]))
        return lines, entries, rules

    def _total(self, total: Total, rows: Sequence[T]) -> list[str]:
        sums = {
            n: sum((Decimal(str(getattr(r, n))) for r in rows if getattr(r, n) is not None), Decimal(0))
            for n in total.sum
        }
        lead = next((i for i, c in enumerate(self.columns) if c.stub), 0)
        return [
            escape(total.label) if i == lead else c.fmt.tex(sums[c.name]) if c.name in sums else ""
            for i, c in enumerate(self.columns)
        ]

    def _group_label(self, key: object) -> str:
        assert self.group_by is not None  # noqa: S101  # only called for a grouped table
        column = _column(self.model, self.group_by)
        return (column.fmt if column else Text()).tex(key)

    def _matching(self, where: Callable[[T], bool] | None) -> list[int]:
        return [i for i, row in enumerate(self.data) if where is None or where(row)]

    def _layout(self, header: list[str]) -> _Layout:
        """The lines of the body, group labels and subtotals among them, and the table row of each thing."""
        names = [c.name for c in self.columns]
        covered: dict[int, set[int]] = {}  # data row -> the columns a span covers
        for span in self.spans:
            start = names.index(span.column)
            for i in self._matching(span.where):
                covered.setdefault(i, set()).update(range(start + 1, start + span.count))
        out = _Layout(list(header))
        done = 0
        for key, members in self.groups:
            if self.group_by is not None:
                out.lines.append(_line([self._group_label(key), *[""] * (len(names) - 1)]))
                out.labels.append(len(out.lines))
            first = len(out.lines) + 1
            for row in members:
                cells = [c.fmt.tex(getattr(row, c.name)) for c in self.columns]
                out.lines.append(_line(["" if j in covered.get(done, ()) else x for j, x in enumerate(cells)]))
                out.position.append(len(out.lines))
                done += 1
            out.indents.append((first, len(out.lines)))
            if self.subtotal is not None:
                out.lines.append(_line(self._total(self.subtotal, members)))
                out.subtotals.append(len(out.lines))
        return out

    def _column_entries(self) -> list[Entry]:
        found: list[Entry] = []
        for i, c in enumerate(self.columns, start=1):
            width = c.width
            spec = t.ColumnSpec(
                halign=c.align,
                wd=width if isinstance(width, Length) else None,
                co=width.n if isinstance(width, Flex) else None,
            )
            found += [t.column(i, spec), *([t.column(i, c.style)] if c.style is not None else [])]
        return found

    def _structure_entries(self, layout: _Layout) -> list[Entry]:
        """Group labels, the gap and indent of groups, and the subtotal rows."""
        look, ruled = self.look, self.look.rules is Rules.BOOKTABS
        label = t.CellSpec(halign=t.HAlign.LEFT, font=look.group_font)
        across = t.CellSpan(c=len(self.columns))
        found = [t.cell(row, 1, label, span=across) for row in layout.labels]
        found += [t.hborder(row, t.HborderSpec(abovespace=look.group_gap)) for row in layout.labels[1:]]
        if self.group_by is not None:
            indent = Raw(rf"\hspace{{{look.indent}}}")
            found += [
                t.cell(t.selector(*_ranges(list(range(a, b + 1)))), 1, t.CellSpec(preto=indent))
                for a, b in layout.indents
            ]
        for row in layout.subtotals:
            found.append(t.row(row, t.RowSpec(font=look.total_font)))
            if ruled:
                found.append(t.hline(row, t.HlineSpec(wd=look.light)))
        return found

    def _styled(self, position: Sequence[int]) -> list[Entry]:
        """The entries for the body spans and the highlights, by the table row of each row of data."""
        names = [c.name for c in self.columns]
        found: list[Entry] = []
        for span in self.spans:
            rows = [position[i] for i in self._matching(span.where)]
            if rows:
                merged = t.CellSpan(c=span.count)
                found.append(
                    t.cell(t.selector(*_ranges(rows)), names.index(span.column) + 1, t.CellSpec(), span=merged)
                )
        for hl in self.highlights:
            rows = [position[i] for i in self._matching(hl.where)]
            if not rows:
                continue
            where, font = t.selector(*_ranges(rows)), _font(hl.bold, hl.font)
            if hl.columns is None:
                found.append(t.row(where, t.RowSpec(bg=hl.bg, fg=hl.fg, font=font)))
            else:
                cols = t.selector(*_ranges([names.index(n) + 1 for n in hl.columns]))
                found.append(t.cell(where, cols, t.CellSpec(bg=hl.bg, fg=hl.fg, font=font)))
        return found

    def node(self) -> t.Tblr | t.Talltblr | t.Longtblr:
        """The table as a `tabularray` environment, typed down to its keys."""
        header, spans, under = self._header()
        h, last, look = len(header), len(self.columns), self.look
        ruled, grid = look.rules is Rules.BOOKTABS, look.rules is Rules.GRID
        layout = self._layout(header)
        rules: list[Entry] = []
        if ruled:
            rules += [t.hline(1, t.HlineSpec(wd=look.heavy)), *under, t.hline(h + 1, t.HlineSpec(wd=look.light))]
        rules.append(
            t.row(
                t.selector(*_ranges(list(range(1, h + 1)))),
                t.RowSpec(font=look.header_font, bg=look.header_bg, fg=look.header_fg),
            )
        )
        if ruled:
            rules += [
                t.column(1, t.ColumnSpec(leftsep=Length("0pt"))),
                t.column(last, t.ColumnSpec(rightsep=Length("0pt"))),
            ]
        # The columns' entries come before the cells': a cell's own alignment wins.
        rules += [*self._column_entries(), *spans, *self._structure_entries(layout), *self._styled(layout.position)]
        for k, total in enumerate(self.totals):
            layout.lines.append(_line(self._total(total, self.data)))
            rules.append(t.row(len(layout.lines), t.RowSpec(font=look.total_font)))
            if k == 0 and ruled:
                rules.append(t.hline(len(layout.lines), t.HlineSpec(wd=look.light)))
        if ruled:
            rules.append(t.hline(t.selector("Z"), t.HlineSpec(wd=look.heavy)))
        inner = t.TblrInner(
            colspec=Raw("Q" * last),
            width=self.width,
            rowsep=look.rowsep,
            colsep=look.colsep,
            rowhead=h if self.long else None,
            hlines=t.HlineSpec(wd=look.light) if grid else None,
            vlines=t.VlineSpec(wd=look.light) if grid else None,
            rules=[*rules, *self.rules],
        )
        outer = t.TblrOuter(
            caption=self.caption,
            label=Raw(self.label) if self.label else None,
            rules=[t.remark(Raw(escape(n.tag)), Raw(escape(n.text))) for n in self.notes] or None,
        )
        env = t.Longtblr if self.long else t.Talltblr if self.caption or self.notes else t.Tblr
        content = Passthrough(Raw("\n".join(layout.lines)))
        return env(content, outer=outer if self.caption or self.notes or self.label else None, inner=inner)

    def render(self) -> str:
        return self.node().render()


__all__ = [
    "Col",
    "Date",
    "Flex",
    "Format",
    "Highlight",
    "Label",
    "Look",
    "Money",
    "Note",
    "Number",
    "Percent",
    "Rules",
    "Span",
    "Table",
    "Text",
    "Total",
]
