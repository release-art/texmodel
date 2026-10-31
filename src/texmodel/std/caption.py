r"""caption: Caption style.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.interface import SQUARE, arg
from texmodel.package import Package
from texmodel.types import Raw, Text

package = Package("caption", prefix="", adopted=True)


@package.command
class CaptionSetup(Command):
    r"""Set caption options: `\captionsetup{font=small,labelfont=bf}`."""

    cs = "captionsetup"
    options: Raw


@package.command
class CaptionOf(Command):
    r"""A caption outside a float: `\captionof{figure}{Text}`."""

    cs = "captionof"
    kind: Raw
    short: Text | None = arg(SQUARE, default=None)
    text: Text
