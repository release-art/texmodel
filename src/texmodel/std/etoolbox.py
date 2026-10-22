r"""etoolbox: Patching and programming tools.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from typing import Annotated

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw, ValueKind

package = Package("etoolbox", prefix="", adopted=True)


@package.command
class Appto(Command):
    r"""Append code to a macro."""

    cs = "appto"
    macro: Raw
    code: Raw


@package.command
class GAppto(Command):
    r"""Append code to a macro, globally."""

    cs = "gappto"
    macro: Raw
    code: Raw


@package.command
class Preto(Command):
    r"""Prepend code to a macro."""

    cs = "preto"
    macro: Raw
    code: Raw


@package.command
class GPreto(Command):
    r"""Prepend code to a macro, globally."""

    cs = "gpreto"
    macro: Raw
    code: Raw


@package.command
class IfBlank(Command):
    r"""Choose by whether an argument is blank."""

    cs = "ifblank"
    argument: Raw
    yes: Raw
    no: Raw


@package.command
class IfStrEqual(Command):
    r"""Choose by whether two strings are equal."""

    cs = "ifstrequal"
    first: Raw
    second: Raw
    yes: Raw
    no: Raw


@package.command
class NewToggle(Command):
    r"""Declare a switch."""

    cs = "newtoggle"
    name: Raw


@package.command
class ToggleTrue(Command):
    r"""Set a switch to true."""

    cs = "toggletrue"
    name: Raw


@package.command
class ToggleFalse(Command):
    r"""Set a switch to false."""

    cs = "togglefalse"
    name: Raw


@package.command
class SetToggle(Command):
    r"""Set a switch to `true` or `false`."""

    cs = "settoggle"
    name: Raw
    value: Raw


@package.command
class IfToggle(Command):
    r"""Choose by a switch."""

    cs = "iftoggle"
    name: Raw
    yes: Raw
    no: Raw


@package.command
class AtBeginEnvironment(Command):
    r"""Code at the start of an environment."""

    cs = "AtBeginEnvironment"
    environment: Raw
    code: Raw


@package.command
class AtEndEnvironment(Command):
    r"""Code at the end of an environment."""

    cs = "AtEndEnvironment"
    environment: Raw
    code: Raw


def _toggle_setting(prefix: str, name: str, value: bool, _alias: str | None) -> str:  # noqa: FBT001
    return (ToggleTrue if value else ToggleFalse)(Raw(f"{prefix}{name}")).render()


TOGGLE = ValueKind(
    "Toggle",
    bool,
    "boolean",
    lambda prefix, name, _alias: (("control", f"{prefix}{name}", f"\\{prefix}{name}"),),
    lambda prefix, name, default, alias: [
        NewToggle(Raw(f"{prefix}{name}")).render(),
        *([] if default is None else [_toggle_setting(prefix, name, default, alias)]),
    ],
    _toggle_setting,
    needs=(package,),
)
Toggle = Annotated[bool, TOGGLE]
"""`Value[Toggle]`: an etoolbox toggle (`\\newtoggle`, `\\toggletrue`), not a `\\newif`; written through the bindings
above."""
