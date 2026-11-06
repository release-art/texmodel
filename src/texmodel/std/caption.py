r"""caption: Caption style.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

import enum

from texmodel.components import Command
from texmodel.interface import SQUARE, Item, Switch, arg
from texmodel.keys import KEYVAL
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import Choice, Length, Name, Raw, Text

package = Package("caption", prefix="", adopted=True)


@enum.unique
class Justification(Choice):
    """A value of `justification`: how a caption is set."""

    JUSTIFIED = "justified"
    CENTERING = "centering"
    CENTERLAST = "centerlast"
    CENTERFIRST = "centerfirst"
    RAGGEDRIGHT = "raggedright"
    RAGGEDLEFT = "raggedleft"


@enum.unique
class LabelSeparator(Choice):
    """A value of `labelsep`: what stands between the label and the text."""

    NONE = "none"
    COLON = "colon"
    PERIOD = "period"
    SPACE = "space"
    QUAD = "quad"
    NEWLINE = "newline"
    ENDASH = "endash"


@enum.unique
class CaptionFormat(Choice):
    """A value of `format`: the text lines up under the label (`hang`) or not (`plain`)."""

    PLAIN = "plain"
    HANG = "hang"


@enum.unique
class Position(Choice):
    """A value of `position`: where a caption sits relative to what it names."""

    TOP = "top"
    BOTTOM = "bottom"
    ABOVE = "above"
    BELOW = "below"


class CaptionOptions(KeyVals, rules=KEYVAL):
    r"""The keys of `\captionsetup`: `CaptionOptions(font=("small",), labelfont=("bf",))`. The font keys take
    attributes (`small`, `bf`, `it`); `extra` takes the rest."""

    font: tuple[Text, ...] | None = None
    labelfont: tuple[Text, ...] | None = None
    textfont: tuple[Text, ...] | None = None
    labelsep: LabelSeparator | None = None
    justification: Justification | None = None
    format: CaptionFormat | None = None
    position: Position | None = None
    singlelinecheck: Switch | None = None
    skip: Length | None = None
    width: Length | None = None
    margin: Length | None = None
    extra: Item[Raw] | None = None


@package.command
class CaptionSetup(Command):
    r"""Set caption options: `\captionsetup{font=small,labelfont=bf}`."""

    cs = "captionsetup"
    options: CaptionOptions


@package.command
class CaptionOf(Command):
    r"""A caption outside a float: `\captionof{figure}{Text}`."""

    cs = "captionof"
    kind: Name
    short: Text | None = arg(SQUARE, default=None)
    text: Text
