r"""geometry: Page dimensions.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw

package = Package("geometry", prefix="", adopted=True)


@package.command
class Geometry(Command):
    r"""Set page dimensions: `\geometry{a4paper,margin=10mm}`."""

    cs = "geometry"
    options: Raw
