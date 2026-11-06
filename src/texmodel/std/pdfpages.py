r"""pdfpages: Pages of other PDFs.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

import dataclasses
import re

from texmodel.components import Command
from texmodel.errors import ValueRuleError
from texmodel.interface import Flag, Item
from texmodel.keys import KEYVAL
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import AsTeX, FilePath, Macro, Raw

package = Package("pdfpages", prefix="", adopted=True)


_PAGE = r"(?:\d+|last)"
_RANGE = re.compile(rf"(?:{_PAGE}(?:-{_PAGE}?)?|-{_PAGE}?|\{{\}})")


@dataclasses.dataclass(frozen=True)
class PageRanges(AsTeX):
    """The pages to place, in order: `PageRanges(("1-3", "5", "last"))` is `1-3,5,last`. A range is `N`, `N-M`, `N-`,
    `-M` or `-` (all), `last` can stand for a number (`last-1` runs backwards), and `{}` is a blank page (`TM-C045`)."""

    ranges: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.ranges or not all(_RANGE.fullmatch(r) for r in self.ranges):
            raise ValueRuleError(
                f"page ranges {self.ranges!r}: give pages such as 1, 2-4, 5-, -3, last or {{}}",
                code="TM-C045",
                hint='PageRanges(("1-3", "5"))',
            )

    def render(self) -> str:
        return ",".join(self.ranges)


@dataclasses.dataclass(frozen=True)
class Nup(AsTeX):
    """Pages per sheet, columns by rows: `Nup(2, 1)` is `2x1`."""

    columns: int
    rows: int

    def __post_init__(self) -> None:
        if self.columns < 1 or self.rows < 1:
            raise ValueRuleError(f"Nup({self.columns}, {self.rows}): give 1 or more", code="TM-C047", hint="Nup(2, 1)")

    def render(self) -> str:
        return f"{self.columns}x{self.rows}"


class IncludePdfOptions(KeyVals, rules=KEYVAL):
    r"""The keys of `\includepdf`: `IncludePdfOptions(pages=PageRanges(("1-3",)), nup=Nup(2, 1))`."""

    pages: PageRanges | None = None
    nup: Nup | None = None
    angle: float | None = None
    scale: float | None = None
    landscape: Flag = False
    frame: Flag = False
    extra: Item[Raw] | None = None


@package.command
class IncludePdf(Command):
    r"""Place pages of a PDF: `\includepdf[pages=-]{a.pdf}`."""

    cs = "includepdf"
    options: IncludePdfOptions | None = None
    path: FilePath | Macro
