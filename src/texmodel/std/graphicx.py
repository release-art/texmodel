r"""graphicx: Pictures: `\includegraphics` and where to look for them.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw

package = Package("graphicx", prefix="", adopted=True)


@package.command
class IncludeGraphics(Command):
    r"""Place a picture: `\includegraphics[width=3cm]{a.png}`."""

    cs = "includegraphics"
    path: Raw
    options: Raw | None = None


@package.command
class GraphicsPath(Command):
    r"""Directories searched for pictures; the first group `{}` keeps the current one."""

    cs = "graphicspath"
    directories: Raw
