r"""subcaption: Captioned parts of a figure.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw, Text

package = Package("subcaption", prefix="", adopted=True)


@package.command
class SubCaption(Command):
    r"""The caption of a part: `\subcaption{Text}`, in a `minipage`."""

    cs = "subcaption"
    text: Text


@package.command
class SubCaptionBox(Command):
    r"""A part with its caption, side by side with others: `\subcaptionbox{Text}{content}`."""

    cs = "subcaptionbox"
    text: Text
    content: Raw
