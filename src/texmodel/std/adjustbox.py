r"""adjustbox: Boxes scaled, clipped and aligned by keys.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package. The keys
are the ones adjustbox documents; `extra` takes any other, as written."""

import enum

from texmodel.components import Command
from texmodel.interface import Flag, Item, OptionalValue
from texmodel.keys import PGFKEYS
from texmodel.keyvals import KeyVals, key
from texmodel.package import Package
from texmodel.types import Choice, Length, Raw

package = Package("adjustbox", prefix="", adopted=True)


@enum.unique
class VAlign(Choice):
    """Where the box sits on the line."""

    TOP = "t"
    MIDDLE = "m"
    BOTTOM = "b"


class AdjustBoxOptions(KeyVals, rules=PGFKEYS):
    r"""The keys of `\adjustbox`: `AdjustBoxOptions(max_width=Length.expr(r"\linewidth"), center=True)`."""

    width: Length | None = None
    height: Length | None = None
    totalheight: Length | None = None
    max_width: Length | None = key("max width")
    max_height: Length | None = key("max height")
    max_totalheight: Length | None = key("max totalheight")
    min_width: Length | None = key("min width")
    min_height: Length | None = key("min height")
    scale: float | None = None
    angle: float | None = None
    margin: Length | None = None
    padding: Length | None = None
    frame: OptionalValue[Length] | None = None
    clip: Flag = False
    center: Flag = False
    valign: VAlign | None = None
    extra: Item[Raw] | None = None


@package.command
class AdjustBox(Command):
    r"""Adjust some content: `\adjustbox{max width=\linewidth}{content}`. (The environment form,
    `\begin{adjustbox}{...}`, is the same macro; declare only one of the two.)"""

    cs = "adjustbox"
    options: AdjustBoxOptions
    content: Raw
