r"""pgfplots: Plots.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package. An axis
stands in a `tikz.Tikzpicture`. A plot (`\addplot coordinates {...};`) has its own syntax and is written in an axis as
`Passthrough`, as TikZ's paths are. To use pgfplots only when the document loads it, put the calls in
`latex.IfPackageLoadedT` inside `latex.AtBeginDocument`."""

import dataclasses
import enum

from texmodel.components import Anywhere, ColourRef, Command, Environment, Passthrough
from texmodel.interface import Flag, Item
from texmodel.keys import PGFKEYS
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import AsTeX, Choice, Length, Name, NameList, Raw, Text

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


@dataclasses.dataclass(frozen=True)
class Colormap(AsTeX):
    r"""A colour map of evenly spaced colours, each as three values from 0 to 255: the value of the `colormap` key.
    `Colormap("brand", ((0, 0, 255), (255, 0, 0)))` is `{brand}{rgb255=(0,0,255) rgb255=(255,0,0)}`."""

    name: str
    colours: tuple[tuple[int, int, int], ...]

    def __post_init__(self) -> None:
        if not self.name.replace(" ", "").isalnum():
            raise ValueError(f"colormap name {self.name!r}: give letters, digits and spaces")
        if len(self.colours) < 2 or any(len(c) != 3 or not all(0 <= x <= 255 for x in c) for c in self.colours):
            raise ValueError(f"colormap {self.name!r}: give two or more colours of three values from 0 to 255")

    def render(self) -> str:
        return f"{{{self.name}}}{{{' '.join('rgb255=(%d,%d,%d)' % c for c in self.colours)}}}"


class PlotStyle(KeyVals, rules=PGFKEYS):
    """One entry of a cycle list, the style of a plot; `extra` takes the rest (`mark options={fill=white}`)."""

    color: ColourRef | None = None
    mark: Text | None = None
    mark_size: Length | None = None
    line_width: Length | None = None
    fill: ColourRef | None = None
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
            raise ValueError("a cycle list: give it a style")

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
    cycle_list_name: Name | None = None
    colormap_name: Name | None = None
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
    name: Name
    styles: CycleList


@package.command
class AddLegendEntry(Command):
    r"""The legend text of the plot before it: `\addlegendentry{Series}`."""

    cs = "addlegendentry"
    text: Text
