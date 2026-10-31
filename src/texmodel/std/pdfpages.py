r"""pdfpages: Pages of other PDFs.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.interface import Flag, Item
from texmodel.keys import KEYVAL
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import FilePath, Raw

package = Package("pdfpages", prefix="", adopted=True)


class IncludePdfOptions(KeyVals, rules=KEYVAL):
    r"""The keys of `\includepdf`: `IncludePdfOptions(pages=Raw("1-3"), nup=Raw("2x1"))`."""

    pages: Raw | None = None
    nup: Raw | None = None
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
    path: FilePath
