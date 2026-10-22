r"""tikz: TikZ. Only what fits the model:
its path commands (`\draw`, `\node`, `\fill`, `\clip`) have their own syntax
and are written as `Passthrough` or `Raw`.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Anywhere, Command, Environment, Passthrough
from texmodel.package import Package
from texmodel.types import Raw

package = Package("tikz", prefix="", adopted=True)


@package.environment
class Tikzpicture(Environment):
    r"""A TikZ picture; its content is TikZ source."""

    cs = "tikzpicture"
    children = [Anywhere(Passthrough)]
    options: Raw | None = None


@package.command
class UseTikzLibrary(Command):
    r"""Load TikZ libraries: `\usetikzlibrary{calc,positioning}`."""

    cs = "usetikzlibrary"
    libraries: Raw


@package.command
class TikzSet(Command):
    r"""Set TikZ keys or styles."""

    cs = "tikzset"
    options: Raw
