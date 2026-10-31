r"""setspace: Line spacing.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw

package = Package("setspace", prefix="", adopted=True)


@package.command
class SetStretch(Command):
    r"""Set the line spacing from here on: `\setstretch{1.25}`."""

    cs = "setstretch"
    factor: Raw


@package.command
class SingleSpacing(Command):
    r"""Single line spacing."""

    cs = "singlespacing"


@package.command
class OneAndHalfSpacing(Command):
    r"""One and a half line spacing."""

    cs = "onehalfspacing"


@package.command
class DoubleSpacing(Command):
    r"""Double line spacing."""

    cs = "doublespacing"
