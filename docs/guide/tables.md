# Tables

`texmodel.ext.table` sets a table from a row model: a pydantic model whose fields are the columns, and its rows. It
writes a `tabularray` environment ([the typed header](std.md)) with booktabs-style rules. The blocks on this page run in
order, as one module.

```python
from typing import Annotated

from pydantic import BaseModel

from texmodel.document import Document
from texmodel.ext.table import Col, Note, Number, Percent, Table, Total
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

`Col(label, fmt=, align=, width=, unit=, group=, stub=, hide=, style=)` on a field says how its column reads. `label`
defaults to the field's name, spaced. A field of type `str`, `Raw` or `int` has a default format; any other type needs
`fmt=` (`TM-M078`), so a number is never written at a precision nobody chose. `group` names a header group: consecutive
columns with the same name share a spanner, and a tuple nests them (`("2025", "H1")`). `width` is a `Length`, or
`Flex(n)` for a share of the table's `width`. `style` is a `tabularray` `ColumnSpec`, the escape hatch for one column.

## Formats

A format turns a value into escaped TeX; nothing else writes a cell, so no `&` or `\\` is written by hand.

| Format | Writes |
|---|---|
| `Text()` | text, escaped; a `Raw` as written; `None` as `–` |
| `Number(decimals, thousands=True, point=".", separator=r"\,", sign=False, minus="−")` | `1 234.50`, rounded half up, a true minus |
| `Percent(decimals)` | a fraction as a percentage, `12.3 %` |

Numbers are right-aligned at one number of decimals per column, which puts the points in line; a column that needs
mixed precision is `Text` with the digits written by the program.

```python
assert Number(2, point="{,}").tex(1234.5) == r"1\,234{,}50"
assert Percent(0).tex(0.5) == r"50\,\%"
assert Number(0).tex(None) == "–"
```

## The parts

`caption` and `notes` make a `Talltblr` (it can sit in a float); `long=True` makes a `Longtblr` that repeats the header on
every page; otherwise a `Tblr`. `Total("Total", sum=("q1", "q2"))` adds a row of sums in the columns' formats under a
rule. `Look` sets the typography: rule weights, padding and the header font; the default is booktabs'. `rules=` takes
more `tabularray` entries, written last, so they win.

```python
from texmodel.ext.table import Look
from texmodel.std.tabularray import RowSpec, row
from texmodel.types import Length

striking = Table(Sale, rows, look=Look(heavy=Length("1pt")), rules=[row(2, RowSpec(font=None))])
assert "hline{1}={wd=1pt}" in striking.render()
```

A row that does not validate is an error naming its index (`TM-C026`); a group on separated columns, a second stub or a
total over a column that is not a visible number is a `DeclarationError` when the table is built (`TM-M077` to `TM-M080`).
