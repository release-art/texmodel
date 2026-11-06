r"""fancyhdr: Running headers and footers.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

import dataclasses
import re

from texmodel.components import Command
from texmodel.errors import ValueRuleError
from texmodel.interface import SQUARE, arg
from texmodel.package import Package
from texmodel.types import AsTeX, Raw

package = Package("fancyhdr", prefix="", adopted=True)


@dataclasses.dataclass(frozen=True)
class Places(AsTeX):
    """Which fields a call sets, the selector in brackets: `Places(("LE", "RO"))` is `LE,RO`. A place has `L`, `C` or
    `R` (left, centre, right), `E` or `O` (even or odd pages) and `H` or `F` (header or footer, for `Fancyhf`), each at
    most once and in any order (`TM-C044`)."""

    places: tuple[str, ...]

    def __post_init__(self) -> None:
        for place in self.places:
            if not re.fullmatch(r"[LCREOHF]+", place) or any(
                len(set(place) & set(group)) > 1 or len(set(place)) != len(place) for group in ("LCR", "EO", "HF")
            ):
                raise ValueRuleError(
                    f"place {place!r}: give L, C or R, E or O and H or F, each once",
                    code="TM-C044",
                    hint='Places(("LE", "RO"))',
                )
        if not self.places:
            raise ValueRuleError("Places: give a place", code="TM-C044", hint='Places(("C",))')

    def render(self) -> str:
        return ",".join(self.places)


@package.command
class Fancyhf(Command):
    r"""Set the header or footer fields: `\fancyhf{}` clears all, `\fancyhf[CH]{text}` sets the centre header."""

    cs = "fancyhf"
    where: Places | None = arg(SQUARE, default=None)
    text: Raw


@package.command
class Fancyhead(Command):
    r"""Set header fields: `\fancyhead[L]{text}`."""

    cs = "fancyhead"
    where: Places | None = arg(SQUARE, default=None)
    text: Raw


@package.command
class Fancyfoot(Command):
    r"""Set footer fields: `\fancyfoot[C]{\thepage}`."""

    cs = "fancyfoot"
    where: Places | None = arg(SQUARE, default=None)
    text: Raw
