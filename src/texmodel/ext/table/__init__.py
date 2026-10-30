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

from ._columns import Col, Flex, Widest
from ._formats import Block, Date, Format, Image, Label, Money, Number, Percent, Text
from ._parts import Highlight, Look, Note, Rules, Span, Total
from ._table import Table

__all__ = [
    "Block",
    "Col",
    "Date",
    "Flex",
    "Format",
    "Highlight",
    "Image",
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
    "Widest",
]
