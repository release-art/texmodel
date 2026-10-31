"""The parts of a table besides its columns."""

import dataclasses
import enum
from collections.abc import Callable
from typing import ClassVar

from ...components import ColourRef
from ...types import Length, Raw

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
    under the header, no padding at the edges (`edge`; `None` keeps `colsep` there, as `GRID` and `PLAIN` do), a bold
    header and totals. `header_bg` and `header_fg` take a colour value. A row group's label is `group_font`, set
    `group_gap` below the group before; its rows are indented."""

    rules: Rules = Rules.BOOKTABS
    heavy: Length = Length("0.08em")
    light: Length = Length("0.05em")
    rowsep: Length = Length("0.5ex")
    colsep: Length = Length("6pt")
    edge: Length | None = Length("0pt")
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
Look.GRID = Look(rules=Rules.GRID, rowsep=Length("2pt"), edge=None)
Look.PLAIN = Look(rules=Rules.NONE, edge=None)
