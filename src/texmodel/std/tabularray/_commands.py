"""The commands of tabularray and its libraries."""

from texmodel.components import Command
from texmodel.interface import SQUARE, arg
from texmodel.types import Length, Raw

from ._specs import (
    CellSpan,
    CellSpec,
    ColumnSpec,
    HborderSpec,
    HlineSpec,
    RowSpec,
    Selector,
    TblrInner,
    TblrOuter,
    VborderSpec,
    VlineSpec,
    package,
)

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
