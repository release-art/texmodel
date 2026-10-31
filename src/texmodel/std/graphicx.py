r"""graphicx: Pictures: `\includegraphics` and where to look for them.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.interface import Flag, Item
from texmodel.keys import KEYVAL
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import FilePath, Length, Macro, Raw, Text

package = Package("graphicx", prefix="", adopted=True)


class IncludeGraphicsOptions(KeyVals, rules=KEYVAL):
    r"""The keys of `\includegraphics` (graphicx reads them with `keyval`):
    `IncludeGraphicsOptions(width=Length("3cm"))`."""

    width: Length | None = None
    height: Length | None = None
    totalheight: Length | None = None
    keepaspectratio: Flag = False
    scale: float | None = None
    angle: float | None = None
    page: int | None = None
    clip: Flag = False
    draft: Flag = False
    trim: Raw | None = None  # four lengths, left bottom right top, cut off when `clip` is set
    alt: Text | None = None  # the text for a tagged PDF (LaTeX 2024-11 and later)
    artifact: Flag = False  # a picture that is decoration, which a tagged PDF leaves out
    extra: Item[Raw] | None = None


@package.command
class IncludeGraphics(Command):
    r"""Place a picture: `\includegraphics[width=3cm]{a.png}`. `path` is a `FilePath` (a checked
    file name) or a `Macro` (`\figdir{a}`, or a bare `ControlSequence`) that expands to it."""

    cs = "includegraphics"
    path: FilePath | Macro
    options: IncludeGraphicsOptions | None = None


@package.command
class GraphicsPath(Command):
    r"""Directories searched for pictures; the first group `{}` keeps the current one."""

    cs = "graphicspath"
    directories: Raw
