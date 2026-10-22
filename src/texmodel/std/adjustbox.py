r"""adjustbox: Boxes scaled, clipped and aligned by keys.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw

package = Package("adjustbox", prefix="", adopted=True)


@package.command
class AdjustBox(Command):
    r"""Adjust some content: `\adjustbox{max width=\linewidth}{content}`. (The environment form,
    `\begin{adjustbox}{...}`, is the same macro; declare only one of the two.)"""

    cs = "adjustbox"
    options: Raw
    content: Raw
