r"""microtype: Micro-typography.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw

package = Package("microtype", prefix="", adopted=True)


@package.command
class MicrotypeSetup(Command):
    r"""Change microtype's options after loading."""

    cs = "microtypesetup"
    options: Raw


@package.command
class SetProtrusion(Command):
    r"""Protrusion of characters: `\SetProtrusion[name=x]{encoding=*}{A={50,50}}`."""

    cs = "SetProtrusion"
    set: Raw
    list: Raw
    options: Raw | None = None
