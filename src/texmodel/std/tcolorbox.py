r"""tcolorbox: Coloured boxes.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Anywhere, Command, Environment, Passthrough
from texmodel.interface import ColourName, Flag, Item
from texmodel.keys import PGFKEYS
from texmodel.keyvals import KeyVals, key
from texmodel.package import Package
from texmodel.types import Length, Raw

package = Package("tcolorbox", prefix="", adopted=True)


class TcolorboxOptions(KeyVals, rules=PGFKEYS):
    """Common tcolorbox keys (it reads them with `pgfkeys`); `extra` takes the rest, as written. Keys of a library
    (`enhanced`, `breakable`) need it loaded with `TcbUseLibrary`."""

    colback: ColourName | None = None
    colframe: ColourName | None = None
    coltext: ColourName | None = None
    boxrule: Length | None = None
    arc: Length | None = None
    left: Length | None = None
    right: Length | None = None
    top: Length | None = None
    bottom: Length | None = None
    width: Length | None = None
    height: Length | None = None
    opacityback: float | None = None
    sharp_corners: Flag = key("sharp corners", default=False)
    enhanced: Flag = False
    breakable: Flag = False
    extra: Item[Raw] | None = None


@package.environment
class Tcolorbox(Environment):
    r"""A coloured box: `\begin{tcolorbox}[colback=white]`."""

    cs = "tcolorbox"
    children = [Anywhere(Passthrough)]
    options: TcolorboxOptions | None = None


@package.command
class TcbUseLibrary(Command):
    r"""Load tcolorbox libraries: `\tcbuselibrary{skins}`."""

    cs = "tcbuselibrary"
    libraries: Raw


@package.command
class TcbSet(Command):
    r"""Set tcolorbox keys."""

    cs = "tcbset"
    options: TcolorboxOptions


@package.command
class Tcbox(Command):
    r"""A coloured box around some text, sized to it."""

    cs = "tcbox"
    text: Raw
    options: TcolorboxOptions | None = None
