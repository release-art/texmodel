r"""tcolorbox: Coloured boxes.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Anywhere, Command, Environment, Passthrough
from texmodel.package import Package
from texmodel.types import Raw

package = Package("tcolorbox", prefix="", adopted=True)


@package.environment
class Tcolorbox(Environment):
    r"""A coloured box: `\begin{tcolorbox}[colback=white]`."""

    cs = "tcolorbox"
    children = [Anywhere(Passthrough)]
    options: Raw | None = None


@package.command
class TcbUseLibrary(Command):
    r"""Load tcolorbox libraries: `\tcbuselibrary{skins}`."""

    cs = "tcbuselibrary"
    libraries: Raw


@package.command
class TcbSet(Command):
    r"""Set tcolorbox keys."""

    cs = "tcbset"
    options: Raw


@package.command
class Tcbox(Command):
    r"""A coloured box around some text, sized to it."""

    cs = "tcbox"
    text: Raw
    options: Raw | None = None
