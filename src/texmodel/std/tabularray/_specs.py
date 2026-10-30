"""Selectors, choices, key lists and entries of tabularray."""

import dataclasses
import enum
import re

from texmodel.components import ColourRef
from texmodel.errors import DeclarationError
from texmodel.interface import Flag, Item, OptionalValue
from texmodel.keys import L3KEYS
from texmodel.keyvals import Entry, KeyVals, key
from texmodel.package import Package
from texmodel.std import xcolor
from texmodel.types import Choice, ControlSequence, Length, Raw, Text

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
    cmd: ControlSequence | None = None
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
    cmd: ControlSequence | None = None
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
    cmd: ControlSequence | None = None
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
