r"""tikz: TikZ. Only what fits the model:
its path commands (`\draw`, `\node`, `\fill`, `\clip`) have their own syntax
and are written as `Passthrough` or `Raw`.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Anywhere, Command, Environment, Passthrough
from texmodel.interface import ColourName, Flag, Item, OptionalValue
from texmodel.keys import PGFKEYS
from texmodel.keyvals import KeyVals, key
from texmodel.package import Package
from texmodel.types import Length, Raw

package = Package("tikz", prefix="", adopted=True)


class TikzOptions(KeyVals, rules=PGFKEYS):
    """Common TikZ keys (pgfkeys); `extra` takes the rest, as written: arrow tips (`->`), `every node/.style=...`."""

    scale: float | None = None
    xscale: float | None = None
    yscale: float | None = None
    rotate: float | None = None
    xshift: Length | None = None
    yshift: Length | None = None
    line_width: Length | None = key("line width")
    draw: ColourName | None = None
    fill: ColourName | None = None
    text: ColourName | None = None
    opacity: float | None = None
    thin: Flag = False
    thick: Flag = False
    dashed: Flag = False
    dotted: Flag = False
    rounded_corners: OptionalValue[Length] | None = key("rounded corners")
    extra: Item[Raw] | None = None


@package.environment
class Tikzpicture(Environment):
    r"""A TikZ picture; its content is TikZ source."""

    cs = "tikzpicture"
    children = [Anywhere(Passthrough)]
    options: TikzOptions | None = None


@package.command
class UseTikzLibrary(Command):
    r"""Load TikZ libraries: `\usetikzlibrary{calc,positioning}`."""

    cs = "usetikzlibrary"
    libraries: Raw


@package.command
class TikzSet(Command):
    r"""Set TikZ keys or styles."""

    cs = "tikzset"
    options: TikzOptions
