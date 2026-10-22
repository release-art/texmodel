r"""eso-pic: Material placed on every page, in absolute positions.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw

package = Package("eso-pic", prefix="", adopted=True)


@package.command
class AddToShipoutPictureBG(Command):
    r"""Add a picture behind the page content."""

    cs = "AddToShipoutPictureBG"
    code: Raw


@package.command
class AddToShipoutPictureFG(Command):
    r"""Add a picture over the page content."""

    cs = "AddToShipoutPictureFG"
    code: Raw


@package.command
class AtPageLowerLeft(Command):
    r"""Put material at the page's lower left corner."""

    cs = "AtPageLowerLeft"
    code: Raw


@package.command
class AtPageUpperLeft(Command):
    r"""Put material at the page's upper left corner."""

    cs = "AtPageUpperLeft"
    code: Raw


@package.command
class AtPageCenter(Command):
    r"""Put material at the page's centre."""

    cs = "AtPageCenter"
    code: Raw
