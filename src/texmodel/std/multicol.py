r"""multicol: Balanced columns.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Anywhere, Command, Environment, Passthrough
from texmodel.package import Package

package = Package("multicol", prefix="", adopted=True)


@package.environment
class Multicols(Environment):
    r"""Text in `columns` balanced columns: `\begin{multicols}{2}`."""

    cs = "multicols"
    children = [Anywhere(Passthrough)]
    columns: int


@package.command
class ColumnBreak(Command):
    r"""Break to the next column."""

    cs = "columnbreak"
