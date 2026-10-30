# Tables

`texmodel.ext.table` sets a table from a row model: a pydantic model whose fields are the columns, and its rows. It
writes a `tabularray` environment ([the typed header](std.md)) with booktabs-style rules. The blocks on this page run in
order, as one module.

```python
from typing import Annotated

from pydantic import BaseModel

from texmodel.document import Document
from texmodel.ext.table import Col, Format, Note, Number, Percent, Table, Total
from texmodel.std import tabularray


class Sale(BaseModel):
    region: Annotated[str, Col("Region", stub=True)]
    q1: Annotated[float, Col("Q1", group="2025", fmt=Number(0))]
    q2: Annotated[float | None, Col("Q2", group="2025", fmt=Number(0))]
    growth: Annotated[float, Col("Growth", fmt=Percent(1, sign=True), unit="%")]


rows = [
    Sale(region="North & Central", q1=1200.5, q2=1340, growth=0.123),
    {"region": "East", "q1": -3, "q2": None, "growth": -0.05},  # a mapping the model validates
]
table = Table(Sale, rows, caption="Revenue", notes=[Note("Provisional.")], totals=[Total("Total", sum=("q1", "q2"))])

document = Document(table.node())
plan = tabularray.package.plan(document)
assert r"North \& Central & 1\,201 & 1\,340 & +12.3\,\% \\" in plan.text
```

## The columns

`Col(label, fmt=, align=, valign=, width=, unit=, group=, stub=, hide=, style=, cells=)` on a field says how its column reads. `label`
defaults to the field's name, spaced. A field of type `str`, `Raw` or `int` has a default format; any other type needs
`fmt=` (`TM-M078`), so a number is never written at a precision nobody chose. `group` names a header group: consecutive
columns with the same name share a spanner, and a tuple nests them (`("2025", "H1")`). `width` is a `Length`, or
`Flex(n)` for a share of the table's `width`. `style` is a `tabularray` `ColumnSpec`, the escape hatch for one column; `cells` is a `CellSpec` for its body rows only
(`cells=CellSpec(font=Raw(r"\ttfamily"))` sets the data in mono and leaves the header alone), and a `Highlight` wins over it.

## Formats

A format turns a value into escaped TeX; nothing else writes a cell, so no `&` or `\\` is written by hand.

| Format | Writes |
|---|---|
| `Text()` | text, escaped; a `Raw` as written; `None` as `–` |
| `Number(decimals, thousands=True, point=".", separator=r"\,", sign=False, minus="−")` | `1 234.50`, rounded half up, a true minus |
| `Percent(decimals)` | a fraction as a percentage, `12.3 %` |
| `Money(decimals=2, symbol="€", after=False)` | an amount with its currency symbol, before or after |
| `Date("%d %b %Y")` | a `date` or `datetime` by a `strftime` pattern (English names) |
| `Label({True: "Yes", False: "No"})` | the text for each value of an enum, a boolean or a code |

Numbers are right-aligned at one number of decimals per column, which puts the points in line; a column that needs
mixed precision is `Text` with the digits written by the program.

```python
assert Number(2, point="{,}").tex(1234.5) == r"1\,234{,}50"
assert Percent(0).tex(0.5) == r"50\,\%"
assert Number(0).tex(None) == "–"
```

## Blocks, pictures and tables in cells

`Block()` writes a cell in a group of its own: a minipage, a list, a paragraph in a column with a `width`, or another
table (`Raw(inner.render())`). The group keeps an `&` or `\\` inside it from ending the cell. `Image(width)` writes a
picture from its path. Both align at the head of the row (`valign=h`), the one alignment that keeps a picture and its
neighbours' text on the same top line; `Col(valign=)` chooses another. A list or display maths in a cell needs
`Table(blocks=True)` (`measure=vbox`) and `\UseTblrLibrary{varwidth}` in the preamble, a picture needs `graphicx`: the
document's package requires them, as the table writes only the table.

```python
from texmodel.ext.table import Block, Image
from texmodel.std.tabularray import CellSpec
from texmodel.types import Length, Raw

class Item(BaseModel):
    name: Annotated[str, Col("Name", cells=CellSpec(font=Raw(r"\ttfamily")))]
    logo: Annotated[str, Col("Logo", fmt=Image(Length("1cm")), width=Length("1.2cm"))]
    about: Annotated[Raw, Col("About", fmt=Block(), width=Length("4cm"))]

items = [Item(name="a", logo="a.png", about=Raw(r"\begin{itemize}\item one\item two\end{itemize}"))]
cell = Table(Item, items, blocks=True).render()
assert r"{\includegraphics[width=1cm]{a.png}}" in cell and "measure=vbox" in cell
```

## Row groups, highlights and spans

`group_by="region"` sets runs of equal values under a label row, in the field's format, with the rows indented; the field is
not a column, and equal values must be next to each other (`TM-M081`). `subtotal=Total(...)` adds a row of sums under each
group. `Highlight(where, columns=, bg=, fg=, bold=, font=)` styles the rows where a predicate holds, or only the cells of
`columns`, and `Span("amount", 2, where=)` merges a cell with the one after it, writing the covered cells empty. A colour is
a `ColourName` or a colour value (`bg=Ink`); the `tabularray` header requires `xcolor`, so it is loaded with it.

```python
from texmodel.ext.table import Highlight, Label, Money, Span


class Stock(BaseModel):
    region: str
    city: Annotated[str, Col("City", stub=True)]
    amount: Annotated[float, Col("Amount", fmt=Money(symbol="€"))]
    ok: Annotated[bool, Col("OK", fmt=Label({True: "Yes", False: "No"}))]


stock = [
    Stock(region="North", city="A", amount=1000, ok=True),
    Stock(region="North", city="B", amount=-5.5, ok=False),
    Stock(region="South", city="C", amount=7, ok=True),
]
grouped = Table(
    Stock,
    stock,
    group_by="region",
    subtotal=Total("Subtotal", sum=("amount",)),
    highlights=[Highlight(lambda r: r.amount < 0, columns=("amount",), bold=True)],
    spans=[Span("amount", 2, where=lambda r: r.city == "C")],
)
assert r"Subtotal & €994.50 &  \\" in grouped.render()
```

## The parts

`caption` and `notes` make a `Talltblr` (it can sit in a float); `long=True` makes a `Longtblr` that repeats the header on
every page; otherwise a `Tblr`. `Total("Total", sum=("q1", "q2"))` adds a row of sums in the columns' formats under a
rule. `Look` sets the typography: rule weights, padding and the fonts of the header, totals and group labels. The default
`Look.BOOKTABS` has no vertical rules; `Look.GRID` is a grid of light rules and `Look.PLAIN` has none. `rules=` takes more
`tabularray` entries, written last, so they win.

```python
from texmodel.ext.table import Look
from texmodel.std.tabularray import RowSpec, row
from texmodel.types import Length

striking = Table(Sale, rows, look=Look(heavy=Length("1pt")), rules=[row(2, RowSpec(font=None))])
assert "hline{1}={wd=1pt}" in striking.render()
```

`header=False` writes no header row and no rule under it: a block of rows whose columns need no labels (a column with a
`group` is refused, `TM-M083`). An empty `Col` label is still a header row; the flag is the explicit way. `Look.edge` is the
padding of the first column's left edge and the last one's right edge: `0pt` by default, so a table starts flush at the margin;
`None` keeps `colsep` there, as `Look.GRID` and `Look.PLAIN` do. `rules=` entries are written last, so they win over either.

## A format of your own

`Format` is a frozen dataclass that a project may subclass, as `Block` and `Image` are: write `_tex(value)`, which returns
escaped TeX, and set the class attributes `align`, `valign` and `numeric` for the column it writes. `missing` stands for
`None`, as in the built-in formats. Nothing else writes a cell, so a format must escape what it takes.

```python
import dataclasses

from texmodel.std.tabularray import HAlign
from texmodel.types import escape


@dataclasses.dataclass(frozen=True)
class Glyph(Format):
    """A glyph of the project's vocabulary, centred."""

    align = HAlign.CENTRE

    def _tex(self, value: object) -> str:
        return rf"\textsf{{{escape(str(value))}}}"


class Profile(BaseModel):
    icon: Annotated[str, Col("", fmt=Glyph(), width=Length("6mm"))]
    label: Annotated[str, Col("")]
    value: Annotated[str, Col("", cells=CellSpec(font=Raw(r"\bfseries")))]


block = Table(Profile, [Profile(icon="a", label="Sound", value="Loud")], header=False, look=Look.PLAIN)
assert block.render().splitlines()[1] == r"\textsf{a} & Sound & Loud \\"
```

A colour that a macro names, read when the document is typeset, is `ColourName.macro(r"\bbRowLabelColour")`
([Values](values.md#colour-names)): `Col(cells=CellSpec(fg=ColourName.macro(...)))` colours a column by it.

## Rows that are nodes

A block of rows that a document edits cell by cell, in the tree, the schema and `Plan.edits`, is set from row commands: a
`std.tabularray.TableRow` of the project's package, one cell per field in order (write a `body` to say otherwise:
`\SetCell`, a cell of your own). `Table(RowClass, rows)` builds it, with the header as one `Passthrough` and the row
commands as typed children; `Col` still sets the width, alignment and style of each column, and the table lists the commands
in tabularray's `expand` key, which makes it expand them before it splits the body at `&`.

```python
from texmodel.package import Package
from texmodel.types import Text

pkg = Package("acme-profile", prefix="ap")


@pkg.command
class ProfileRow(tabularray.TableRow):
    """An icon, a label and a value."""

    icon: Annotated[Raw, Col("", width=Length("6mm"))]
    label: Annotated[Text, Col("")]
    value: Annotated[Text, Col("", cells=CellSpec(font=Raw(r"\bfseries")))]


profile = Table(ProfileRow, [ProfileRow(icon=Raw("a"), label="Sound", value="Loud")], header=False, look=Look.PLAIN)
shown = profile.render()
assert shown.startswith(r"\begin{tblr}[expand=\apProfileRow]") and r"  \apProfileRow{a}{Sound}{Loud}" in shown
```

A row command is a plain `\newcommand` with mandatory arguments only (`TM-M084`), because that is what tabularray expands;
a row command that calls another lists both in `expand`. A table written by hand lists them with `expand_of(rows)`, and a
row whose command is missing from it is `TM-C027` before TeX fails. The cells are written by the row, so `fmt=`, `totals`,
`subtotal`, `group_by` and `spans` are refused (`TM-M085`); `highlights`, `look`, `caption`, `notes`, `long` and the column
keys work. `read_edits` stubs the `tblr` environments too whenever a row is stubbed (a table processes its body four times);
`stub=` adds other components. Reordering rows or adding a row line is not restorable (`TM-R006`, `TM-R005`), as for any
container.

## A column as wide as the widest cell

Several tables that sit one under the other, such as profile blocks, read as one design when their label columns are
equally wide: as wide as the widest label of any of them. `Widest.declare(pkg, "LabelWidth")` declares the length
(`\apLabelWidth`, a `Recorded` maximum, [Values](values.md#values-only-the-whole-document-knows)) and the command that
measures a cell; `Col(width=widest)` in each table sets the column to that length and has its cells measure themselves
(`tabularray`'s `cmd`), the header label too. It works for plain tables and for rows that are nodes.

```python
from texmodel.ext.table import Widest

widest = Widest.declare(pkg, "LabelWidth")


class Line(BaseModel):
    label: Annotated[str, Col("Label", width=widest)]
    value: str


shown = Table(Line, [Line(label="Sound", value="Loud")], look=Look.PLAIN).render()
assert r"column{1}={halign=l,wd=\apLabelWidth}" in shown and r"cmd=\apMeasureLabelWidth" in shown
```

The widths are measured in one run and used in the next, so the first run sets the column to nothing and says the value is
not settled: let `latexmk` rerun, as for any `Recorded`. A cell that does not typeset the same on every pass (a box LaTeX
defers) does not settle.

A row that does not validate is an error naming its index (`TM-C026`); a group on separated columns, a second stub or a
total over a column that is not a visible number is a `DeclarationError` when the table is built (`TM-M077` to `TM-M082`).
