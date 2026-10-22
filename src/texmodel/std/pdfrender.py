r"""pdfrender: PDF text rendering modes.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw

package = Package("pdfrender", prefix="", adopted=True)


@package.command
class PdfRender(Command):
    r"""Set text rendering for the group: `\pdfrender{TextRenderingMode=2,LineWidth=0.4pt}`."""

    cs = "pdfrender"
    options: Raw
