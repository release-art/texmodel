"""The table."""

import dataclasses
import itertools
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from decimal import Decimal
from typing import Any

import pydantic

from ...components import Passthrough
from ...errors import DeclarationError, ValidationError
from ...keyvals import Entry
from ...std import tabularray as t
from ...types import Length, Raw, escape
from ._columns import Column, Flex, Widest, column_of, columns_of
from ._formats import Text
from ._parts import Highlight, Look, Note, Rules, Span, Total

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


def check_cells(layout: type, count: int, rows: Iterable[tuple[str, type]]) -> None:
    """A row command writes as many cells as the layout has columns: its body's `&`, counted as text."""
    if not issubclass(layout, t.TableRow):
        return
    for where, row in rows:
        tex: list[dict[str, str]] = [vars(k).get("__tm_tex__", {}) for k in row.__mro__]
        text = next((d["body"] for d in tex if "body" in d), "")
        cells = len(re.findall(r"(?<!\\)&", text)) + 1
        if text and cells != count:
            raise DeclarationError(
                f"{where}: {row.__name__} writes {cells} cells, the layout {layout.__name__} has {count} columns",
                code="TM-M086",
                path=where,
                hint="write one cell per column in the body (an empty cell is `&` with nothing after it)",
            )


@dataclasses.dataclass(frozen=True)
class Table[T: pydantic.BaseModel]:
    """A row model and its rows, with the parts of a table. `rows` are instances of the model, or mappings it validates;
    `node()` is the `tabularray` environment, `render()` its TeX. `group_by` names a field whose runs of equal values
    become row groups, each under a label row (the field is not a column), with a `subtotal` row if given. `blocks`
    measures cells as boxes, which a list or display maths in a cell needs (`\\UseTblrLibrary{varwidth}`).
    `header=False` writes no header row: a block of rows whose columns need no labels (a `group` is refused)."""

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
    header: bool = True
    long: bool = False
    width: Length | None = None
    blocks: bool = False
    rules: Sequence[Entry] = ()
    columns: tuple[Column, ...] = dataclasses.field(init=False, repr=False)
    data: tuple[T, ...] = dataclasses.field(init=False, repr=False)
    groups: tuple[tuple[object, tuple[T, ...]], ...] = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        columns = columns_of(self.model, self.group_by)
        self._check(columns)
        body: list[T] = []
        for i, row in enumerate(self.rows):
            if isinstance(row, t.TableRow if issubclass(self.model, t.TableRow) else self.model):
                body.append(row)  # a node row of any class: its command writes the cells, the model only the columns
                continue
            try:
                body.append(self.model.model_validate(row))
            except pydantic.ValidationError as exc:
                raise ValidationError(f"row {i}: {exc}", code="TM-C026", path=f"rows[{i}]") from exc
        self._check_cells(body, len(columns))
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

    def _check_cells(self, body: Sequence[T], count: int) -> None:
        check_cells(self.model, count, [(f"rows[{i}]", type(row)) for i, row in enumerate(body)])

    def _check_node_rows(self) -> None:
        """Rows that are nodes are written by their own command: what writes cells in a plain table has no part."""
        where = self.model.__name__
        for part, used in (("totals", self.totals), ("subtotal", self.subtotal), ("group_by", self.group_by)):
            if used:
                raise DeclarationError(
                    f"Table: {part} is not set from rows that are nodes: the row command writes the cells",
                    code="TM-M085",
                    path=where,
                    hint="compute the row in the program, or use a plain row model",
                )
        if self.spans:
            raise DeclarationError(
                "Table: spans are not set from rows that are nodes: use \\SetCell in the row's body",
                code="TM-M085",
                path=where,
            )

    def _check(self, columns: tuple[Column, ...]) -> None:
        """The parts name columns that are there and fit."""
        index = {c.name: i for i, c in enumerate(columns)}
        where = self.model.__name__
        if issubclass(self.model, t.TableRow):
            self._check_node_rows()
        if not self.header and any(c.group for c in columns):
            raise DeclarationError(
                "Table: header groups need a header",
                code="TM-M083",
                path=where,
                hint="drop the groups of the columns, or leave header=True",
            )
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
        if not self.header:
            return [], [], []
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
        column = column_of(self.model, self.group_by)
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
                cells = (
                    [""] * len(names)  # the row command writes them
                    if issubclass(self.model, t.TableRow)
                    else [c.fmt.tex(getattr(row, c.name)) for c in self.columns]
                )
                out.lines.append(_line(["" if j in covered.get(done, ()) else x for j, x in enumerate(cells)]))
                out.position.append(len(out.lines))
                done += 1
            out.indents.append((first, len(out.lines)))
            if self.subtotal is not None:
                out.lines.append(_line(self._total(self.subtotal, members)))
                out.subtotals.append(len(out.lines))
        return out

    def _column_entries(self, position: Sequence[int], labels: int, *, every: bool = False) -> list[Entry]:
        found: list[Entry] = []
        for i, c in enumerate(self.columns, start=1):
            width = c.width
            spec = t.ColumnSpec(
                halign=c.align,
                valign=c.valign,
                wd=width.length if isinstance(width, Widest) else width if isinstance(width, Length) else None,
                co=width.n if isinstance(width, Flex) else None,
            )
            found += [t.column(i, spec), *([t.column(i, c.style)] if c.style is not None else [])]
            if c.cells is not None and (position or every):
                found.append(t.cell(t.selector(*_ranges(position)) if position else t.selector("-"), i, c.cells))
            if isinstance(width, Widest):  # the cells measure themselves, the labels too
                measured = [*([labels] if labels else []), *position]
                where = t.selector(*_ranges(measured)) if measured else t.selector("-")
                found.append(t.cell(where, i, t.CellSpec(cmd=width.cmd)))
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
        return self._node(every=False)

    def _node(self, *, every: bool) -> t.Tblr | t.Talltblr | t.Longtblr:
        """`every`: a layout of no rows yet, whose cell styles and measurement apply to every row."""
        header, spans, under = self._header()
        h, last, look = len(header), len(self.columns), self.look
        ruled, grid = look.rules is Rules.BOOKTABS, look.rules is Rules.GRID
        layout = self._layout(header)
        rules: list[Entry] = []
        if ruled:
            rules += [t.hline(1, t.HlineSpec(wd=look.heavy)), *under]
            if h:
                rules.append(t.hline(h + 1, t.HlineSpec(wd=look.light)))
        if h:
            rules.append(
                t.row(
                    t.selector(*_ranges(list(range(1, h + 1)))),
                    t.RowSpec(font=look.header_font, bg=look.header_bg, fg=look.header_fg),
                )
            )
        if look.edge is not None:
            rules += [t.column(1, t.ColumnSpec(leftsep=look.edge)), t.column(last, t.ColumnSpec(rightsep=look.edge))]
        # The columns' entries come before the cells': a cell's own alignment wins.
        rules += [
            *self._column_entries(layout.position, h, every=every),
            *spans,
            *self._structure_entries(layout),
            *self._styled(layout.position),
        ]
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
            measure=t.Measure.VBOX if self.blocks else None,
            rowhead=h if self.long and h else None,
            hlines=t.HlineSpec(wd=look.light) if grid else None,
            vlines=t.VlineSpec(wd=look.light) if grid else None,
            rules=[*rules, *self.rules],
        )
        nodes = [r for r in self.data if isinstance(r, t.TableRow)]  # the rows of a table of nodes
        outer = t.TblrOuter(
            caption=self.caption,
            label=Raw(self.label) if self.label else None,
            expand=t.expand_of(nodes) if nodes else None,
            rules=[t.remark(Raw(escape(n.tag)), Raw(escape(n.text))) for n in self.notes] or None,
        )
        env = t.Longtblr if self.long else t.Talltblr if self.caption or self.notes else t.Tblr
        if issubclass(self.model, t.TableRow):
            head = [Passthrough(Raw("\n".join(layout.lines[:h])))] if h else []
            return env(*head, *nodes, outer=outer, inner=inner)
        content = Passthrough(Raw("\n".join(layout.lines)))
        return env(content, outer=outer if self.caption or self.notes or self.label else None, inner=inner)

    def render(self) -> str:
        return self.node().render()
