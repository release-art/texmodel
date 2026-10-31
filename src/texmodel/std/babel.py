r"""babel: Languages for pdfTeX (and LuaTeX with babel).

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Name, Text

package = Package("babel", prefix="", adopted=True)


@package.command
class SelectLanguage(Command):
    r"""Switch the language from here on: `\selectlanguage{english}`."""

    cs = "selectlanguage"
    language: Name


@package.command
class ForeignLanguage(Command):
    r"""Typeset a short text in another language: `\foreignlanguage{german}{Text}`."""

    cs = "foreignlanguage"
    language: Name
    text: Text
