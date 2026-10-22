r"""geometry: Page dimensions.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.interface import Flag, Item
from texmodel.keys import KEYVAL
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import Length, Raw

package = Package("geometry", prefix="", adopted=True)


class GeometryOptions(KeyVals, rules=KEYVAL):
    r"""The page keys: `GeometryOptions(a4paper=True, margin=Length("10mm"))`. Other paper names (`letterpaper`) and
    keys go in `extra`, as written."""

    a4paper: Flag = False
    a5paper: Flag = False
    letterpaper: Flag = False
    landscape: Flag = False
    margin: Length | None = None
    left: Length | None = None
    right: Length | None = None
    top: Length | None = None
    bottom: Length | None = None
    inner: Length | None = None
    outer: Length | None = None
    paperwidth: Length | None = None
    paperheight: Length | None = None
    textwidth: Length | None = None
    textheight: Length | None = None
    bindingoffset: Length | None = None
    headsep: Length | None = None
    footskip: Length | None = None
    includehead: Flag = False
    includefoot: Flag = False
    centering: Flag = False
    showframe: Flag = False
    extra: Item[Raw] | None = None


@package.command
class Geometry(Command):
    r"""Set page dimensions: `\geometry{a4paper,margin=10mm}`."""

    cs = "geometry"
    options: GeometryOptions
