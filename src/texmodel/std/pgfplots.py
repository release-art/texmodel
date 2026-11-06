r"""pgfplots: Plots.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package. An axis
stands in a `tikz.Tikzpicture`. A plot (`\addplot coordinates {...};`) has its own syntax and is written in an axis as
`Passthrough`, as TikZ's paths are. To use pgfplots only when the document loads it, put the calls in
`latex.IfPackageLoadedT` inside `latex.AtBeginDocument`."""

import dataclasses
import enum
import re

from texmodel.components import Anywhere, ColourRef, Command, Environment, Passthrough
from texmodel.errors import ValueRuleError
from texmodel.interface import ColourName, Flag, Item
from texmodel.keys import PGFKEYS
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import AsTeX, Choice, Length, NameList, Raw, Text

package = Package("pgfplots", prefix="", adopted=True)


@enum.unique
class Grid(Choice):
    """A value of `grid`: which lines are drawn."""

    MAJOR = "major"
    MINOR = "minor"
    BOTH = "both"
    NONE = "none"


@enum.unique
class AxisLines(Choice):
    """A value of `axis lines`: how the axes are drawn."""

    BOX = "box"
    LEFT = "left"
    MIDDLE = "middle"
    CENTER = "center"
    NONE = "none"


_PLOT_NAME = re.compile(r"[A-Za-z][A-Za-z0-9-]*(?: [A-Za-z0-9-]+)*")


@dataclasses.dataclass(frozen=True)
class PlotName(Raw):
    """The name of a cycle list or a colour map, as pgfplots takes it: words of letters, digits and `-` with single
    spaces between, starting with a letter (`PlotName("brand bars")`)."""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not _PLOT_NAME.fullmatch(self.tex):
            raise ValueRuleError(
                f"plot name {self.tex!r}: give words of letters, digits and `-` with single spaces",
                code="TM-C037",
                hint='PlotName("brand bars")',
            )


type Stop = tuple[int, int, int] | ColourRef
"""A colour of a colour map: three values from 0 to 255, or a colour by name."""


@dataclasses.dataclass(frozen=True)
class Colormap(AsTeX):
    r"""A colour map of evenly spaced colours, each as three values from 0 to 255 or a colour by name, the value of the
    `colormap` key. `Colormap(PlotName("brand"), ((0, 0, 255), ColourName("red")))` is
    `{brand}{rgb255=(0,0,255) color=(red)}`. A named stop follows the colour's definition, so it keeps the colour model
    the package loads with (`[cmyk]`), where a triple is always RGB."""

    name: PlotName
    colours: tuple[Stop, ...]

    def __post_init__(self) -> None:
        stops = tuple(c if isinstance(c, tuple) else ColourName(c) for c in self.colours)
        if len(stops) < 2 or any(
            isinstance(c, tuple) and (len(c) != 3 or not all(0 <= x <= 255 for x in c)) for c in stops
        ):
            raise ValueRuleError(
                f"colormap {self.name.tex!r}: give two or more colours, each three values from 0 to 255 or a name",
                code="TM-C038",
                hint="(0, 0, 255) or ColourName('ink')",
            )
        object.__setattr__(self, "colours", stops)

    def render(self) -> str:
        stops = (f"rgb255=({c[0]},{c[1]},{c[2]})" if isinstance(c, tuple) else f"color=({c})" for c in self.colours)
        return f"{{{self.name.tex}}}{{{' '.join(stops)}}}"


class PlotStyle(KeyVals, rules=PGFKEYS):
    """One entry of a cycle list, the style of a plot; `extra` takes the rest (`mark options={fill=white}`)."""

    color: ColourRef | None = None
    mark: Text | None = None
    mark_size: Length | None = None
    line_width: Length | None = None
    fill: ColourRef | None = None
    draw: ColourRef | None = None
    opacity: float | None = None
    solid: Flag = False
    dashed: Flag = False
    dotted: Flag = False
    only_marks: Flag = False
    no_marks: Flag = False
    extra: Item[Raw] | None = None


@dataclasses.dataclass(frozen=True)
class CycleList(AsTeX):
    r"""The styles of a cycle list, one per plot, in order: `CycleList((PlotStyle(...), PlotStyle(...)))` is
    `{color=red}\\{color=blue}\\`."""

    styles: tuple[PlotStyle, ...]

    def __post_init__(self) -> None:
        if not self.styles:
            raise ValueRuleError("a cycle list: give it a style", code="TM-C039", hint="CycleList((PlotStyle(...),))")

    def render(self) -> str:
        return "".join("{" + style.render() + r"}\\" for style in self.styles)


class PgfplotsOptions(KeyVals, rules=PGFKEYS):
    r"""Common axis and `\pgfplotsset` keys; `extra` takes the rest, as written (`legend style={draw=none}`)."""

    compat: Text | None = None
    width: Length | None = None
    height: Length | None = None
    xmin: float | None = None
    xmax: float | None = None
    ymin: float | None = None
    ymax: float | None = None
    xlabel: Text | None = None
    ylabel: Text | None = None
    title: Text | None = None
    legend_pos: Text | None = None
    grid: Grid | None = None
    axis_lines: AxisLines | None = None
    xtick: tuple[float, ...] | None = None
    ytick: tuple[float, ...] | None = None
    xbar: Flag = False
    ybar: Flag = False
    scale_only_axis: Flag = False
    colorbar: Flag = False
    cycle_list_name: PlotName | None = None
    colormap_name: PlotName | None = None
    colormap: Colormap | None = None
    extra: Item[Raw] | None = None


@package.environment
class Axis(Environment):
    r"""A plot with linear axes: `\begin{axis}[xlabel=x]`."""

    cs = "axis"
    children = [Anywhere(Passthrough)]
    options: PgfplotsOptions | None = None


@package.environment
class SemilogxAxis(Environment):
    r"""A plot with a logarithmic x axis."""

    cs = "semilogxaxis"
    children = [Anywhere(Passthrough)]
    options: PgfplotsOptions | None = None


@package.environment
class SemilogyAxis(Environment):
    r"""A plot with a logarithmic y axis."""

    cs = "semilogyaxis"
    children = [Anywhere(Passthrough)]
    options: PgfplotsOptions | None = None


@package.environment
class LoglogAxis(Environment):
    r"""A plot with logarithmic axes."""

    cs = "loglogaxis"
    children = [Anywhere(Passthrough)]
    options: PgfplotsOptions | None = None


@package.command
class UsePgfplotsLibrary(Command):
    r"""Load pgfplots libraries: `\usepgfplotslibrary{groupplots}`."""

    cs = "usepgfplotslibrary"
    libraries: NameList


@package.command
class PgfplotsSet(Command):
    r"""Set pgfplots keys for the rest of the group: `\pgfplotsset{compat=1.18}`."""

    cs = "pgfplotsset"
    options: PgfplotsOptions


@package.command
class PgfplotsCreatePlotCycleList(Command):
    r"""Name a cycle list, to use as `cycle list name=`."""

    cs = "pgfplotscreateplotcyclelist"
    name: PlotName
    styles: CycleList


@package.command
class AddLegendEntry(Command):
    r"""The legend text of the plot before it: `\addlegendentry{Series}`."""

    cs = "addlegendentry"
    text: Text
