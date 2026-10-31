r"""hyperref: Links and PDF metadata.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.interface import Flag, Item
from texmodel.keys import KEYVAL
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import Raw, Text

package = Package("hyperref", prefix="", adopted=True)


class HypersetupOptions(KeyVals, rules=KEYVAL):
    r"""The keys of `\hypersetup`: `HypersetupOptions(pdftitle="Deck", hidelinks=True)`. Other keys go in `extra`."""

    pdftitle: Text | None = None
    pdfauthor: Text | None = None
    pdfsubject: Text | None = None
    pdfkeywords: Text | None = None
    colorlinks: Flag = False
    hidelinks: Flag = False
    linkcolor: Raw | None = None
    urlcolor: Raw | None = None
    bookmarks: Flag = False
    extra: Item[Raw] | None = None


@package.command
class Hypersetup(Command):
    r"""Set hyperref's options after loading: `\hypersetup{pdftitle={Deck}}`."""

    cs = "hypersetup"
    options: HypersetupOptions


@package.command
class Href(Command):
    r"""A link with text: `\href{https://example.org}{text}`."""

    cs = "href"
    url: Raw
    text: Text


@package.command
class Url(Command):
    r"""A link shown as its address: `\url{https://example.org}`."""

    cs = "url"
    url: Raw


@package.command
class HyperTarget(Command):
    r"""A named place a link can jump to: `\hypertarget{name}{text}`."""

    cs = "hypertarget"
    name: Raw
    text: Text


@package.command
class HyperLink(Command):
    r"""A link to a `HyperTarget`: `\hyperlink{name}{text}`."""

    cs = "hyperlink"
    name: Raw
    text: Text
