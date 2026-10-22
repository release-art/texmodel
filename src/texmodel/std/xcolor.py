r"""xcolor: Colours.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw, Text

package = Package("xcolor", prefix="", adopted=True)


@package.command
class DefineColor(Command):
    r"""Name a colour: `\definecolor{ink}{HTML}{223344}`."""

    cs = "definecolor"
    name: Raw
    model: Raw
    spec: Raw


@package.command
class ColorLet(Command):
    r"""Name a colour by mixing others."""

    cs = "colorlet"
    name: Raw
    spec: Raw


@package.command
class Color(Command):
    r"""Switch the text colour: `\color{ink}` or `\color[rgb]{1,0,0}`."""

    cs = "color"
    name: Raw
    model: Raw | None = None


@package.command
class TextColor(Command):
    r"""Coloured text: `\textcolor{ink}{words}`."""

    cs = "textcolor"
    name: Raw
    text: Text
    model: Raw | None = None
