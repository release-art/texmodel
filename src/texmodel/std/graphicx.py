r"""graphicx: Pictures: `\includegraphics` and where to look for them.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.interface import Flag, Item
from texmodel.keys import KEYVAL
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import Length, Raw

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
    extra: Item[Raw] | None = None


@package.command
class IncludeGraphics(Command):
    r"""Place a picture: `\includegraphics[width=3cm]{a.png}`."""

    cs = "includegraphics"
    path: Raw
    options: IncludeGraphicsOptions | None = None


@package.command
class GraphicsPath(Command):
    r"""Directories searched for pictures; the first group `{}` keeps the current one."""

    cs = "graphicspath"
    directories: Raw
