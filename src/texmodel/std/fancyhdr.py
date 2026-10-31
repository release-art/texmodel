r"""fancyhdr: Running headers and footers.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.interface import SQUARE, arg
from texmodel.package import Package
from texmodel.types import Raw

package = Package("fancyhdr", prefix="", adopted=True)


@package.command
class Fancyhf(Command):
    r"""Set the header or footer fields: `\fancyhf{}` clears all, `\fancyhf[CH]{text}` sets the centre header."""

    cs = "fancyhf"
    where: Raw | None = arg(SQUARE, default=None)
    text: Raw


@package.command
class Fancyhead(Command):
    r"""Set header fields: `\fancyhead[L]{text}`."""

    cs = "fancyhead"
    where: Raw | None = arg(SQUARE, default=None)
    text: Raw


@package.command
class Fancyfoot(Command):
    r"""Set footer fields: `\fancyfoot[C]{\thepage}`."""

    cs = "fancyfoot"
    where: Raw | None = arg(SQUARE, default=None)
    text: Raw
