r"""tabularray: Tables from an inner and an outer key list, with their styles apart from their cells.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package. It covers
the package and the libraries with names of their own (`booktabs`, `diagbox`, `tikz`); a library is loaded with
`UseTblrLibrary`. The cells are TeX between `Passthrough`s, with `&` and `\\` as written.

```python
from texmodel.std.tabularray import CellSpec, HAlign, HlineSpec, Tblr, TblrInner, cell

Tblr(
    Passthrough(Raw(r"a & b \\")),
    inner=TblrInner(colspec=Raw("ll"), hlines=HlineSpec(), rules=[cell(1, 2, CellSpec(halign=HAlign.RIGHT))]),
)  # \begin{tblr}{colspec=ll,hlines={},cell{1}{2}={halign=r}}
```

Keys that carry arguments (`cell{1}{2}`, `row{odd}`, `hline{1,Z}`) are `Entry` items of the `rules` list, built by
`cell`, `row`, `column`, `hline`, `vline`, `hborder` and `vborder` from a `selector`. Not typed: `colspec` and `rowspec`
(a language of their own), the `amsmath` library's `+matrix` family (an environment name has letters only), the
experimental interfaces (child ids and classes, hooks, public variables) and the `functional` library's functions."""

import dataclasses
import enum
import re
from collections.abc import Iterable
from typing import Any

from texmodel._internal.render import newcommand_fits
from texmodel.components import Anywhere, ColourRef, Command, Environment, Node, Passthrough, control_name
from texmodel.errors import DeclarationError, Violation
from texmodel.interface import SQUARE, Flag, Item, OptionalValue, arg
from texmodel.keys import L3KEYS
from texmodel.keyvals import Entry, KeyVals, key
from texmodel.package import Package
from texmodel.std import xcolor
from texmodel.types import Choice, Length, Raw, Text

package = Package("tabularray", prefix="", adopted=True, requires=[xcolor.package])  # a colour key needs xcolor


# --- selectors: which rows, columns, lines ------------------------------------------------------------------------

_INDEX = r"-?\d+|[U-Z](?:\[\d+\])?"
_PART = re.compile(
    rf"(?:{_INDEX})(?:-(?:{_INDEX}))?|(?:odd|even)(?:\[\d+\])?|every(?:\[\d+\])?\{{(?:{_INDEX})\}}\{{(?:{_INDEX})\}}|-"
)


@dataclasses.dataclass(frozen=True)
class Selector(Raw):
    """Which children a key sets, built by `selector`. A user-defined indexer is written `Selector("mine")`."""


type Index = int | str | Selector


def selector(*parts: int | str) -> Selector:
    r"""A child selector: indexes `2`, `-1`, `Z` (last), `Y[2]`; ranges `"2-4"`, `"1-Z[2]"`; `"odd"`, `"even[3]"`,
    `"every[2]{2}{-2}"`; `"-"` for all: `selector(1, "3-5", "Z")` is `1,3-5,Z`."""
    texts = [str(p) for p in parts]
    bad = [t for t in texts if not _PART.fullmatch(t)]
    if not texts or bad:
        raise DeclarationError(
            f"selector({', '.join(map(repr, parts))}): {bad[0]!r} is not an index, range or child selector"
            if bad
            else "selector(): nothing selected",
            code="TM-M076",
            hint="2, -1, Z, Y[2], '2-4', 'odd', 'even[3]', 'every[2]{2}{-2}' or '-'",
        )
    return Selector(",".join(texts))


def _selected(index: Index) -> Selector:
    return index if isinstance(index, Selector) else selector(index)


# --- the choices ---------------------------------------------------------------------------------------------------


@enum.unique
class HAlign(Choice):
    """Horizontal alignment of cell text."""

    JUSTIFY = "j"
    LEFT = "l"
    CENTRE = "c"
    RIGHT = "r"


@enum.unique
class VAlign(Choice):
    """Vertical alignment: top, middle, bottom, head (first baseline) or foot (last baseline)."""

    TOP = "t"
    MIDDLE = "m"
    BOTTOM = "b"
    HEAD = "h"
    FOOT = "f"


@enum.unique
class Mode(Choice):
    """How cell text is typeset."""

    MATH = "math"
    INLINE_MATH = "imath"
    DISPLAY_MATH = "dmath"
    TEXT = "text"


@enum.unique
class Dash(Choice):
    """A rule's style (more are defined with `\\NewTblrDashStyle`)."""

    SOLID = "solid"
    DASHED = "dashed"
    DOTTED = "dotted"


@enum.unique
class Baseline(Choice):
    """Where the table sits on the line: top or middle or bottom, or the first or last row's baseline."""

    TOP = "t"
    FIRST_ROW = "T"
    MIDDLE = "m"
    BOTTOM = "b"
    LAST_ROW = "B"


@enum.unique
class Span(Choice):
    """How the width (`hspan`) or height (`vspan`, no `MINIMAL`) of a spanning cell is shared."""

    DEFAULT = "default"
    EVEN = "even"
    MINIMAL = "minimal"


@enum.unique
class PageBreak(Choice):
    """Whether a long table may break at a border."""

    YES = "yes"
    NO = "no"
    AUTO = "auto"


@enum.unique
class Measure(Choice):
    """How cell widths are measured (the `varwidth` library; `vbox` and `vstore` take lists and display maths)."""

    HBOX = "hbox"
    VBOX = "vbox"
    VSTORE = "vstore"


# --- the key lists of rules, cells, rows, columns and borders -----------------------------------------------------


class HlineSpec(KeyVals, rules=L3KEYS):
    r"""The keys of a horizontal rule: `\hline[...]`, `hline{2}={...}`, `hlines={...}`. `HlineSpec()` is a plain one."""

    dash: Dash | None = None
    text: Raw | None = None
    wd: Length | None = None
    fg: ColourRef | None = None
    leftpos: float | None = None
    rightpos: float | None = None
    l: OptionalValue[float] | None = None  # noqa: E741  # the library's own key
    r: OptionalValue[float] | None = None
    lr: OptionalValue[float] | None = None
    endpos: Flag = False


class VlineSpec(KeyVals, rules=L3KEYS):
    r"""The keys of a vertical rule: `\vline[...]`, `vline{2}={...}`, `vlines={...}`."""

    dash: Dash | None = None
    text: Raw | None = None
    wd: Length | None = None
    fg: ColourRef | None = None
    abovepos: float | None = None
    belowpos: float | None = None


class CellSpan(KeyVals, rules=L3KEYS):
    r"""The rows and columns a cell spans: `\SetCell[r=2,c=3]{...}`."""

    r: int | None = None
    c: int | None = None


class CellSpec(KeyVals, rules=L3KEYS):
    r"""The keys of a cell: `\SetCell{...}`, `cell{1}{2}={...}`, `cells={...}`."""

    halign: HAlign | None = None
    valign: VAlign | None = None
    wd: Length | None = None
    bg: ColourRef | None = None
    fg: ColourRef | None = None
    font: Raw | None = None
    mode: Mode | None = None
    math: Flag = key("$", default=False)
    dmath: Flag = key("$$", default=False)
    cmd: Raw | None = None
    preto: Raw | None = None
    appto: Raw | None = None
    guard: Flag = False  # the siunitx library


class RowSpec(KeyVals, rules=L3KEYS):
    r"""The keys of a row: `\SetRow{...}`, `row{2}={...}`, `rows={...}`. The `_plus` ones add to the value."""

    halign: HAlign | None = None
    valign: VAlign | None = None
    ht: Length | None = None
    bg: ColourRef | None = None
    fg: ColourRef | None = None
    font: Raw | None = None
    mode: Mode | None = None
    math: Flag = key("$", default=False)
    dmath: Flag = key("$$", default=False)
    cmd: Raw | None = None
    abovesep: Length | None = None
    abovesep_plus: Length | None = key("abovesep+")
    belowsep: Length | None = None
    belowsep_plus: Length | None = key("belowsep+")
    rowsep: Length | None = None
    rowsep_plus: Length | None = key("rowsep+")
    preto: Raw | None = None
    appto: Raw | None = None
    guard: Flag = False


class ColumnSpec(KeyVals, rules=L3KEYS):
    r"""The keys of a column: `\SetColumn{...}`, `column{1}={...}`, `columns={...}`, and `Q[...]` in a `colspec`."""

    halign: HAlign | None = None
    valign: VAlign | None = None
    wd: Length | None = None
    co: float | None = None
    bg: ColourRef | None = None
    fg: ColourRef | None = None
    font: Raw | None = None
    mode: Mode | None = None
    math: Flag = key("$", default=False)
    dmath: Flag = key("$$", default=False)
    cmd: Raw | None = None
    leftsep: Length | None = None
    leftsep_plus: Length | None = key("leftsep+")
    rightsep: Length | None = None
    rightsep_plus: Length | None = key("rightsep+")
    colsep: Length | None = None
    colsep_plus: Length | None = key("colsep+")
    preto: Raw | None = None
    appto: Raw | None = None
    guard: Flag = False
    si: Raw | None = None  # the siunitx library: the `S` column's options


class HborderSpec(KeyVals, rules=L3KEYS):
    r"""The keys of the space and break at a horizontal border: `\hborder{...}`, `hborder{2}={...}`."""

    pagebreak: PageBreak | None = None
    abovespace: Length | None = None
    belowspace: Length | None = None
    abovespace_plus: Length | None = key("abovespace+")
    belowspace_plus: Length | None = key("belowspace+")


class VborderSpec(KeyVals, rules=L3KEYS):
    r"""The keys of the space at a vertical border: `\vborder{...}`, `vborder{2}={...}`."""

    leftspace: Length | None = None
    rightspace: Length | None = None
    leftspace_plus: Length | None = key("leftspace+")
    rightspace_plus: Length | None = key("rightspace+")


# --- the entries: keys that carry arguments ----------------------------------------------------------------------


def cell(rows: Index, columns: Index, spec: CellSpec, *, span: CellSpan | None = None) -> Entry:
    """`cell{rows}{columns}={span}{spec}`: styles (and the span) of the cells at those rows and columns."""
    return Entry.of(f"cell{{{_selected(rows).tex}}}{{{_selected(columns).tex}}}", *([span] if span else []), spec)


def cells(spec: CellSpec, *, span: CellSpan | None = None) -> Entry:
    """`cells={span}{spec}`, with a span; `TblrInner(cells=...)` is the one without."""
    return Entry.of("cells", *([span] if span else []), spec)


def row(rows: Index, spec: RowSpec) -> Entry:
    """`row{rows}={spec}`."""
    return Entry.of(f"row{{{_selected(rows).tex}}}", spec)


def column(columns: Index, spec: ColumnSpec) -> Entry:
    """`column{columns}={spec}`."""
    return Entry.of(f"column{{{_selected(columns).tex}}}", spec)


def hline(rows: Index, spec: HlineSpec, *segments: Index) -> Entry:
    """`hline{rows}={segments}{spec}`: the rules above those rows, over the segments (columns) given."""
    return Entry.of(f"hline{{{_selected(rows).tex}}}", *map(_selected, segments), spec)


def vline(columns: Index, spec: VlineSpec, *segments: Index) -> Entry:
    """`vline{columns}={segments}{spec}`: the rules left of those columns, over the segments (rows) given."""
    return Entry.of(f"vline{{{_selected(columns).tex}}}", *map(_selected, segments), spec)


def hlines(spec: HlineSpec, *segments: Index) -> Entry:
    """`hlines={segments}{spec}`, the form that selects segments of every rule."""
    return Entry.of("hlines", *map(_selected, segments), spec)


def vlines(spec: VlineSpec, *segments: Index) -> Entry:
    """`vlines={segments}{spec}`, the form that selects segments of every rule."""
    return Entry.of("vlines", *map(_selected, segments), spec)


def hborder(rows: Index, spec: HborderSpec) -> Entry:
    """`hborder{rows}={spec}`."""
    return Entry.of(f"hborder{{{_selected(rows).tex}}}", spec)


def vborder(columns: Index, spec: VborderSpec) -> Entry:
    """`vborder{columns}={spec}`."""
    return Entry.of(f"vborder{{{_selected(columns).tex}}}", spec)


def note(tag: Raw, text: Raw) -> Entry:
    r"""`note{tag}={text}`, an outer key of a long or tall table: a footnote, cited with `\TblrNote{tag}`."""
    return Entry.of(f"note{{{tag.tex}}}", text)


def remark(tag: Raw, text: Raw) -> Entry:
    """`remark{tag}={text}`, an outer key: a paragraph under the table, headed by its tag."""
    return Entry.of(f"remark{{{tag.tex}}}", text)


# --- the specifications of a table ---------------------------------------------------------------------------------


class TblrInner(KeyVals, rules=L3KEYS):
    r"""The mandatory argument of a table (`\SetTblrInner` takes the same): its layout and styles.
    `rules` holds the keys with arguments (`cell`, `row`, `hline`, ...); `extra` any key not typed here."""

    colspec: Raw | None = None
    rowspec: Raw | None = None
    width: Length | None = None
    rowhead: int | None = None
    rowfoot: int | None = None
    hlines: HlineSpec | None = None
    vlines: VlineSpec | None = None
    cells: CellSpec | None = None
    rows: RowSpec | None = None
    columns: ColumnSpec | None = None
    rulesep: Length | None = None
    stretch: float | None = None
    abovesep: Length | None = None
    belowsep: Length | None = None
    rowsep: Length | None = None
    leftsep: Length | None = None
    rightsep: Length | None = None
    colsep: Length | None = None
    hspan: Span | None = None
    vspan: Span | None = None
    baseline: Baseline | None = None
    measure: Measure | None = None  # the varwidth library
    process: Raw | None = None  # the functional library
    rules: list[Item[Entry]] | None = None
    extra: Item[Raw] | None = None


class TblrOuter(KeyVals, rules=L3KEYS):
    r"""The optional argument of a table (`\SetTblrOuter` takes the same): the caption and notes of a long or tall
    table, and what to expand first. `rules` holds `note(...)` and `remark(...)`."""

    baseline: Baseline | None = None
    long: Flag = False
    tall: Flag = False
    expand: Raw | None = None
    expand_plus: Raw | None = key("expand+")
    evaluate: Raw | None = None  # the functional library
    headsep: Length | None = None
    footsep: Length | None = None
    presep: Length | None = None
    postsep: Length | None = None
    theme: Raw | None = None
    caption: Text | None = None
    entry: Text | None = None
    label: Raw | None = None
    rules: list[Item[Entry]] | None = None
    extra: Item[Raw] | None = None


# --- the commands inside a table ------------------------------------------------------------------------------------


@package.command
class Hline(Command):
    r"""A horizontal rule across the table: `\hline[dashed]`."""

    cs = "hline"
    options: HlineSpec | None = None


@package.command
class Cline(Command):
    r"""A horizontal rule over some columns: `\cline[dashed]{2-3}`."""

    cs = "cline"
    columns: Selector
    options: HlineSpec | None = None


@package.command
class Vline(Command):
    r"""A vertical rule at the start of a cell: `\vline[dashed]`."""

    cs = "vline"
    options: VlineSpec | None = None


@package.command
class Rline(Command):
    r"""A vertical rule over some rows: `\rline[dashed]{2-3}`."""

    cs = "rline"
    rows: Selector
    options: VlineSpec | None = None


@package.command
class Hborder(Command):
    r"""The space and break at the border above this row: `\hborder{abovespace=3pt}`."""

    cs = "hborder"
    spec: HborderSpec


@package.command
class Vborder(Command):
    r"""The space at the border left of this column: `\vborder{leftspace=3pt}`."""

    cs = "vborder"
    spec: VborderSpec


@package.command
class SetHline(Command):
    r"""`hline{i}={index}{columns}{spec}` for the row it starts: `\SetHline[1]{2-3}{dashed}`."""

    cs = "SetHline"
    index: Selector | None = None
    columns: Selector
    spec: HlineSpec


@package.command
class SetHlines(Command):
    r"""`hlines={index}{columns}{spec}`, set from inside the table."""

    cs = "SetHlines"
    index: Selector | None = None
    columns: Selector
    spec: HlineSpec


@package.command
class SetVline(Command):
    r"""`vline{j}={index}{rows}{spec}` for the column it starts."""

    cs = "SetVline"
    index: Selector | None = None
    rows: Selector
    spec: VlineSpec


@package.command
class SetVlines(Command):
    r"""`vlines={index}{rows}{spec}`, set from inside the table."""

    cs = "SetVlines"
    index: Selector | None = None
    rows: Selector
    spec: VlineSpec


@package.command
class SetCell(Command):
    r"""`cell{i}{j}={span}{spec}` for the cell it starts: `\SetCell[r=2,c=3]{halign=c}`."""

    cs = "SetCell"
    span: CellSpan | None = None
    spec: CellSpec


@package.command
class SetCells(Command):
    r"""`cells={span}{spec}`, set from inside the table."""

    cs = "SetCells"
    span: CellSpan | None = None
    spec: CellSpec


@package.command
class SetRow(Command):
    r"""`row{i}={spec}` for the row it starts: `\SetRow{bg=gray}`."""

    cs = "SetRow"
    spec: RowSpec


@package.command
class SetRows(Command):
    r"""`rows={spec}`, set from inside the table."""

    cs = "SetRows"
    spec: RowSpec


@package.command
class SetColumn(Command):
    r"""`column{j}={spec}` for the column it starts."""

    cs = "SetColumn"
    spec: ColumnSpec


@package.command
class SetColumns(Command):
    r"""`columns={spec}`, set from inside the table."""

    cs = "SetColumns"
    spec: ColumnSpec


@package.command
class TblrNote(Command):
    r"""Cite a note of the table: `\TblrNote{a}` (declared by `note(...)` in the outer keys)."""

    cs = "TblrNote"
    tag: Raw


# --- the booktabs library -------------------------------------------------------------------------------------------


@package.command
class Toprule(Command):
    r"""The rule above the table (`booktabs` library): `\toprule[2pt]`."""

    cs = "toprule"
    options: HlineSpec | None = None


@package.command
class Midrule(Command):
    r"""A rule between rows (`booktabs` library)."""

    cs = "midrule"
    options: HlineSpec | None = None


@package.command
class Bottomrule(Command):
    r"""The rule below the table (`booktabs` library)."""

    cs = "bottomrule"
    options: HlineSpec | None = None


@package.command
class Cmidrule(Command):
    r"""A rule over some columns (`booktabs` library): `\cmidrule[lr]{2-3}`."""

    cs = "cmidrule"
    columns: Selector
    options: HlineSpec | None = None


@package.command
class Cmidrulemore(Command):
    r"""Another rule over some columns, under the last (`booktabs` library)."""

    cs = "cmidrulemore"
    columns: Selector
    options: HlineSpec | None = None


@package.command
class Morecmidrules(Command):
    r"""`\morecmidrules\cmidrule{2-4}`: the next `\cmidrule` goes under the last (`booktabs` library)."""

    cs = "morecmidrules"


@package.command
class Specialrule(Command):
    r"""A rule with the space below the row above and above this row (`booktabs` library):
    `\specialrule{0.5pt}{4pt}{6pt}`."""

    cs = "specialrule"
    spec: HlineSpec
    below: Length
    above: Length


@package.command
class Addlinespace(Command):
    r"""Vertical space between rows (`booktabs` library): `\addlinespace[1em]`."""

    cs = "addlinespace"
    space: Length | None = None


@package.command
class Addrowspace(Command):
    r"""Another name of `\addlinespace` (`booktabs` library)."""

    cs = "addrowspace"
    space: Length | None = None


# --- the diagbox library --------------------------------------------------------------------------------------------


@package.command
class Diagbox(Command):
    r"""A cell cut by a diagonal, with two texts (`diagbox` library): `\diagbox{Aa}{Pp}`."""

    cs = "diagbox"
    lower: Raw
    upper: Raw


@package.command
class Diagboxthree(Command):
    r"""A cell cut by two diagonals, with three texts (`diagbox` library)."""

    cs = "diagboxthree"
    lower: Raw
    middle: Raw
    upper: Raw


# --- the environments ------------------------------------------------------------------------------------------------


class TableRow(Command, abstract=True):
    r"""A row a package writes as a command, cells separated by `&` and ended by `\\`: the table expands it before it
    splits the body, so the table lists its commands in `expand` (`expand_of`; a `Table` does it). A subclass has
    mandatory arguments only; without a `body`, each field is one cell, in order (`#icon & #label & #value \\`).
    A row command that calls another lists both."""

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        if not kwargs.get("abstract") and not any("body" in k.__dict__.get("__tm_tex__", {}) for k in cls.__mro__):
            cls.__tm_tex__["body"] = " & ".join(f"#{n}" for n in cls.model_fields) + r" \\"
        super().__pydantic_init_subclass__(**kwargs)
        if not kwargs.get("abstract") and (
            any(a.optional for a in cls.__tm_args__) or not newcommand_fits(cls.__tm_args__)
        ):
            raise DeclarationError(
                f"{cls.__qualname__}: a row command takes mandatory arguments in braces only",
                code="TM-M084",
                path=cls.__name__,
                hint="tabularray expands a plain \\newcommand: an optional or token argument is not expanded",
            )


def expand_of(rows: Iterable[Node]) -> Raw | None:
    r"""The `expand` key for these table children: the commands of the `TableRow`s among them, in order of first use."""
    names = dict.fromkeys(rf"\{control_name(type(r))}" for r in rows if isinstance(r, TableRow))
    return Raw("".join(names)) if names else None


def _expanded(table: Environment, path: str) -> list[Violation]:
    """Every row command of a table is in its `expand` (`TM-C027`): otherwise tabularray splits the body at the `&`
    inside the command and fails with a misplaced alignment tab."""
    outer = getattr(table, "outer", None)
    listed = set(
        re.findall(r"\\[A-Za-z@]+", " ".join(str(getattr(outer, k, None) or "") for k in ("expand", "expand_plus")))
    )
    return [
        Violation(
            "TM-C027",
            f"{path}/{type(row).__name__}[{i}]",
            f"{type(row).__name__}: \\{control_name(type(row))} is not in the table's expand",
            hint="TblrOuter(expand=expand_of(rows))",
        )
        for i, row in enumerate(table.content)
        if isinstance(row, TableRow) and rf"\{control_name(type(row))}" not in listed
    ]


TABLE_BODY = [
    Anywhere(Passthrough),
    Anywhere(TableRow),
    *map(
        Anywhere,
        (
            Hline,
            Cline,
            Vline,
            Rline,
            Hborder,
            Vborder,
            SetHline,
            SetHlines,
            SetVline,
            SetVlines,
            SetCell,
            SetCells,
            SetRow,
            SetRows,
            SetColumn,
            SetColumns,
            TblrNote,
            Toprule,
            Midrule,
            Bottomrule,
            Cmidrule,
            Cmidrulemore,
            Morecmidrules,
            Specialrule,
            Addlinespace,
            Addrowspace,
            Diagbox,
            Diagboxthree,
        ),
    ),
]


@package.environment
class Tblr(Environment):
    r"""A table: `\begin{tblr}[outer]{inner}`."""

    cs = "tblr"
    children = TABLE_BODY
    checks = [_expanded]
    outer: TblrOuter | None = None
    inner: TblrInner


@package.environment
class Longtblr(Environment):
    r"""A table that breaks over pages, with a caption, notes and repeated heads and feet."""

    cs = "longtblr"
    children = TABLE_BODY
    checks = [_expanded]
    outer: TblrOuter | None = None
    inner: TblrInner


@package.environment
class Talltblr(Environment):
    r"""A table with a caption and notes that stays on a page (it can go in a float)."""

    cs = "talltblr"
    children = TABLE_BODY
    checks = [_expanded]
    outer: TblrOuter | None = None
    inner: TblrInner


@package.environment
class Booktabs(Environment):
    r"""A table with `booktabs` rules and no row padding (`booktabs` library)."""

    cs = "booktabs"
    children = TABLE_BODY
    checks = [_expanded]
    outer: TblrOuter | None = None
    inner: TblrInner


@package.environment
class Longtabs(Environment):
    r"""A long `booktabs` table (`booktabs` library)."""

    cs = "longtabs"
    children = TABLE_BODY
    checks = [_expanded]
    outer: TblrOuter | None = None
    inner: TblrInner


@package.environment
class Talltabs(Environment):
    r"""A tall `booktabs` table (`booktabs` library)."""

    cs = "talltabs"
    children = TABLE_BODY
    checks = [_expanded]
    outer: TblrOuter | None = None
    inner: TblrInner


@package.environment
class TblrTikzBelow(Environment):
    r"""TikZ code drawn below the table that follows (`tikz` library): nodes `table`, `<i>-<j>`, `h<i>`, `v<j>`."""

    cs = "tblrtikzbelow"
    children = [Anywhere(Passthrough)]


@package.environment
class TblrTikzAbove(Environment):
    r"""TikZ code drawn above the table that follows (`tikz` library)."""

    cs = "tblrtikzabove"
    children = [Anywhere(Passthrough)]


# --- loading libraries and setting defaults -------------------------------------------------------------------------


@package.command
class UseTblrLibrary(Command):
    r"""Load a library in the preamble: `\UseTblrLibrary{booktabs}`. (`amsmath`, `booktabs`, `counter`, `diagbox`,
    `functional`, `hook`, `html`, `nameref`, `siunitx`, `tikz`, `varwidth`, `zref`.)"""

    cs = "UseTblrLibrary"
    libraries: Raw


@package.command
class SetTblrInner(Command):
    r"""Default inner keys of some tables: `\SetTblrInner[tblr,longtblr]{rowsep=0pt}`."""

    cs = "SetTblrInner"
    environments: Raw | None = None
    spec: TblrInner


@package.command
class SetTblrOuter(Command):
    r"""Default outer keys of some tables: `\SetTblrOuter[longtblr]{headsep=3pt}`."""

    cs = "SetTblrOuter"
    environments: Raw | None = None
    spec: TblrOuter


@package.command
class SetTblrTracing(Command):
    r"""What to log about tables: `\SetTblrTracing{all}`, `{none}` or `{+row,+column}`."""

    cs = "SetTblrTracing"
    what: Raw


# --- defining types, environments, commands, templates and themes -------------------------------------------------


@package.command
class NewTblrColumnType(Command):
    r"""A column type for `colspec`: `\NewTblrColumnType{t}[1]{Q[t,wd=#1]}`; `count` and `default` as `\newcommand`."""

    cs = "NewTblrColumnType"
    name: Raw
    count: int | None = arg(SQUARE, default=None, fill="")
    default: Raw | None = arg(SQUARE, default=None)
    definition: Raw


@package.command
class NewTblrRowType(Command):
    r"""A row type for `rowspec`: `\NewTblrRowType{t}[1]{Q[t,ht=#1]}`."""

    cs = "NewTblrRowType"
    name: Raw
    count: int | None = arg(SQUARE, default=None, fill="")
    default: Raw | None = arg(SQUARE, default=None)
    definition: Raw


@package.command
class NewTblrColumnRowType(Command):
    r"""A type for both `colspec` and `rowspec`."""

    cs = "NewTblrColumnRowType"
    name: Raw
    count: int | None = arg(SQUARE, default=None, fill="")
    default: Raw | None = arg(SQUARE, default=None)
    definition: Raw


@package.command
class NewTblrEnviron(Command):
    r"""A table environment with its own defaults: `\NewTblrEnviron{mytblr}`, then `\SetTblrInner[mytblr]{...}`."""

    cs = "NewTblrEnviron"
    name: Raw


@package.command
class NewTblrTableCommand(Command):
    r"""A command that may change a table's specifications inside it: `\NewTblrTableCommand\myhline{\hline[red]}`."""

    cs = "NewTblrTableCommand"
    name: Raw
    count: int | None = arg(SQUARE, default=None, fill="")
    default: Raw | None = arg(SQUARE, default=None)
    definition: Raw


@package.command
class NewTblrContentCommand(Command):
    r"""A command that holds cell text, to use inside a table: `\NewTblrContentCommand\cellname{...}`."""

    cs = "NewTblrContentCommand"
    name: Raw
    count: int | None = arg(SQUARE, default=None, fill="")
    default: Raw | None = arg(SQUARE, default=None)
    definition: Raw


@package.command
class NewTblrDashStyle(Command):
    r"""A rule style for `dash`: `\NewTblrDashStyle{dashdot}{...}`."""

    cs = "NewTblrDashStyle"
    name: Raw
    definition: Raw


@package.command
class NewTblrTheme(Command):
    r"""A theme for the head and foot of long tables: templates and styles, chosen with `theme=` in the outer keys."""

    cs = "NewTblrTheme"
    name: Raw
    code: Raw


@package.command
class DeclareTblrTemplate(Command):
    r"""A template for a head or foot element: `\DeclareTblrTemplate{conthead-text}{default}{(Continued)}`
    (`default` defines and selects it)."""

    cs = "DeclareTblrTemplate"
    element: Raw
    name: Raw
    code: Raw


@package.command
class SetTblrTemplate(Command):
    r"""Select a template of an element: `\SetTblrTemplate{caption}{empty}`."""

    cs = "SetTblrTemplate"
    element: Raw
    name: Raw


@package.command
class UseTblrTemplate(Command):
    r"""Use a template (and its style), inside another template: `\UseTblrTemplate{caption-tag}{default}`."""

    cs = "UseTblrTemplate"
    element: Raw
    name: Raw


@package.command
class ExpTblrTemplate(Command):
    r"""Use a template without its style."""

    cs = "ExpTblrTemplate"
    element: Raw
    name: Raw


@package.command
class SetTblrStyle(Command):
    r"""The style of a head or foot element: `\SetTblrStyle{firsthead}{font=\bfseries}`."""

    cs = "SetTblrStyle"
    element: Raw
    style: Raw
