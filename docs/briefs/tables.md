# Draft: tables from a row model (`texmodel.ext.table`)

Roadmap §3, "Reports from a pipeline" (plan §21a 20), piece 1. Status: **phases 1 to 3 built** (`texmodel/ext/table.py`, guide page `docs/guide/tables.md`); phase 4 is open. The typed `tabularray`
header (`texmodel.std.tabularray`) is the layer underneath; this is the layer a report author writes against.

## What the survey says

Great Tables / gt, tinytable, Typst, Rich and booktabs (research of 2026-10-30) agree on a few things, and the design
takes each:

| Lesson | Here |
|---|---|
| A table is named parts (caption, stub, header groups, body, totals, notes), and data stays apart from presentation. | A `Table` is a row model, rows and those parts. Cell text is never styled by rewriting it. |
| Alignment, number format, unit and width belong to the column (Rich, Typst), not to selectors. | `Col(...)` on the field of the row model. |
| Spans are structure, not coordinates (tinytable `group_tt`, Typst `colspan`, against ReportLab's corner tuples). | A header group is a name on consecutive columns; a body span is a `Cell(..., colspan=)`. |
| Exceptions take a predicate or a name, not an index. | `Highlight(where=lambda r: ..., columns=("q1",))`. |
| Good typography is the default (booktabs: no verticals, no doubles, rules of two weights, room around them). | The default `Look`; a different one is an explicit choice. |
| Fail early (Typst shifts every later cell when one is missing). | Rows are validated by pydantic when the table is built; a bad group or total is a declaration error. |
| A raw escape hatch beats more options (tinytable's "98% from four verbs"). | `inner=` and `rules=` take the typed `TblrInner` and `Entry` items of the `std` layer. |

## The shape

```py
class Sale(BaseModel):                                # any pydantic model; its fields are the columns, in order
    region: Annotated[str, Col("Region")]
    q1: Annotated[float, Col("Q1", group="2025", fmt=Number(0))]
    q2: Annotated[float, Col("Q2", group="2025", fmt=Number(0))]
    growth: Annotated[float | None, Col("Growth", fmt=Percent(1, sign=True))]

table = Table(
    Sale, rows,                                       # instances, or dicts the model validates
    caption="Revenue by region", unit="EUR k", label="tab:revenue",
    totals=[Total("Total", sum=("q1", "q2"))],        # computed in Python, set apart by a rule
    notes=[Note("Provisional figures.")],
    highlights=[Highlight(where=lambda r: (r.growth or 0) < 0, columns=("growth",), fg=Danger)],
)
Document(table.node())                                # a Tblr / Longtblr of std.tabularray: Passthrough rows, typed keys
```

- **`Col(label, *, fmt, align, width, unit, group, stub, hide, style)`** is the one marker on a field. `label` defaults to
  the field name, spaced. `group` is a name or a tuple of names for header groups (consecutive columns with the same
  name share a spanner; a tuple nests). `width` is a `Length` or `Flex(n)` (tabularray's `X`). `style` is a `CellSpec`
  (the escape hatch for the whole column). `stub` makes it the row-label column.
- **`fmt`** is a pure function value → escaped TeX, a frozen dataclass: `Number(decimals, thousands, point, sign,
  negative, missing)`, `Percent`, `Money(currency)`, `Date(pattern)`, `Label({value: text})` for enums and booleans, and
  `Text` (the default for `str`, escaped). A field typed `Raw` passes as written. The default is by type; a format that does
  not fit the type (`Number` on a `str`) is refused when the table is built.
- **`Table(model, rows, *, caption, label, totals, notes, look, long, width, rules)`** keeps the parts (`group_by`,
  `subtotal`, `highlights` and `spans` are phase 2; `unit` is `Col(unit=)` in the header only; `inner=` is `rules=`);
  `node()` is the std tree, `render()` its TeX.

## Decisions

1. **Numbers are right-aligned at one decimal count per column.** The same number of decimals in a tabular-figure
   font puts the points in line, so no `siunitx` `S` column: no new package, and a cell is plain text. A column that
   needs mixed precision is `Text` with a format of its own. (plan V6: the figures are proved by a compile test.)
2. **A `Look` carries the typography**, a frozen dataclass: rule weights (`heavy`, `light`, default booktabs'
   `0.08em` and `0.05em`), row padding, header font, stub font, banding (off), the colours as `ColourRef`s (`header_bg=Ink`).
   Presets `Look.BOOKTABS` (default), `Look.GRID` and `Look.PLAIN`. Rules are `tabularray`'s own `hline` keys, so the
   `booktabs` library is not loaded.
3. **The table is a builder, not a registered component.** Its output is a std node tree, so it needs no package of
   its own and the document's package requires `tabularray` by itself. Binding a `Table` to JSON or TOML data is §21a 15,
   not here; `rows` already accept what the row model validates, so a dict from data works today.
4. **Long tables are `Longtblr`** with `rowhead` = the header rows (and `rowfoot` for totals) when `long=True`; otherwise
   `Tblr`, or `Talltblr` when it has a caption and notes and must sit in a float. Nothing is guessed from the row count.
5. **No `&` or `\\` is written by hand anywhere**; every cell is escaped by its format, and a property test (any
   string in any cell) proves the output balances and compiles.
6. **Minus sign and missing values**: a negative number uses U+2212 (`−`), a `None` is `–` (both overridable on
   `Number`). Thousands are a thin space `\,`, the point `.`, and a locale is just those settings.
7. **Row groups** (`group_by="region"`), built: a spanning label row in italics with the rows indented under it, a gap
   before each group but the first, and an optional subtotal row under each. A body span is `Span(column, count, where=)`
   and a highlight `Highlight(where, columns=)`, both by predicate on the row: no `Cell(colspan=)` value wrapper, since a
   row field is typed by the model. `Look.GRID` and `Look.PLAIN` are `Rules.GRID` and `Rules.NONE`. (The draft: a spanning label row, or a stub label on the first row of the group, with the
   rows indented under it, and an optional subtotal.)

## Errors (new codes at the time of building)

An unknown column in `totals`, `highlights`, `sum` or a group; groups that are not contiguous; a `sum` over a
non-numeric column; two stubs; a `fmt` that does not fit its field's type; a table with no visible column. All are
`DeclarationError`s naming the class and field; a row that does not validate is pydantic's error with the row index.

## Tests

- Goldens in `tests/examples/` for a plain table, header groups (two levels), totals, notes, highlights and a long
  table; `UPDATE_GOLDEN=1`, read the diff.
- A `tex` compile of each (needs `tabularray` in the reference image: `bin/test-image.sh`, or `TEXMODEL_STD_ON_HOST=1`),
  including a row of the characters `& % $ # _ { } ~ ^ \` in every column, and a 120-row long table breaking over pages
  with the header repeated (the measurement of §21a 20 as a regression).
- `hypothesis` on formats (`Number` round-trips its digits; no format emits an unescaped special) and on the shape
  (rows × columns equals the cells written).

## Phases

1. `Col`, `Text`, `Number`, `Percent`, `Table`, header groups, totals, notes, caption, `Look.BOOKTABS`, `Tblr` / `Longtblr`.
2. Row groups and subtotals, `Highlight`, body `Span`, `Look.GRID` / `PLAIN`, `Money`, `Date`, `Label`. Built.
2b. Rich cells: `Block`, `Image`, `Col.cells`, `Col.valign`, `Table(blocks=True)`. Built (a footnote mark in a cell, `\\verb` in one and loading the libraries from the table stay open).
3. The reference image gets `tabularray` (`docker/test/Dockerfile`: `tabularray`, `ninecolors`, `diagbox`, `pict2e`, `varwidth`); the guide page and a cookbook example. Built.
4. Data binding (§21a 15) and a second consumer, which decide what `Table` still gets wrong.

## Open

- Whether a column's `Col` may also be given beside the model (`Table(Sale, rows, columns={"q1": Col(...)})`) for a model
  one does not own; the annotation is the first choice.
- A table-wide `unit` (decided for phase 1: `Col(unit=)`, in the header, only).
- Footnote marks inside cells (`Note` tied to a cell, `\TblrNote{a}`) not built in phase 2.
