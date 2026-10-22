r"""enumitem: List layout.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw

package = Package("enumitem", prefix="", adopted=True)


@package.command
class SetList(Command):
    r"""Change list settings: `\setlist[itemize]{noitemsep}`."""

    cs = "setlist"
    options: Raw
    lists: Raw | None = None
