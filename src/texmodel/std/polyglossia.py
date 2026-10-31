r"""polyglossia: Languages for XeTeX and LuaTeX.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.interface import SQUARE, arg
from texmodel.package import Package
from texmodel.types import Name, Raw

package = Package("polyglossia", prefix="", adopted=True)


@package.command
class SetMainLanguage(Command):
    r"""The document's language: `\setmainlanguage{english}`."""

    cs = "setmainlanguage"
    options: Raw | None = arg(SQUARE, default=None)
    language: Name


@package.command
class SetOtherLanguage(Command):
    r"""A further language the document uses: `\setotherlanguage{german}`."""

    cs = "setotherlanguage"
    options: Raw | None = arg(SQUARE, default=None)
    language: Name
