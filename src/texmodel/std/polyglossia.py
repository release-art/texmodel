r"""polyglossia: Languages for XeTeX and LuaTeX.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.interface import SQUARE, Item, Switch, arg
from texmodel.keys import KEYVAL
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import Name, Raw, Text

package = Package("polyglossia", prefix="", adopted=True)


class LanguageOptions(KeyVals, rules=KEYVAL):
    r"""The options of a language, `\setmainlanguage[variant=american]{english}`; `extra` takes the rest."""

    variant: Text | None = None
    spelling: Text | None = None
    numerals: Text | None = None
    script: Text | None = None
    calendar: Text | None = None
    babelshorthands: Switch | None = None
    extra: Item[Raw] | None = None


@package.command
class SetMainLanguage(Command):
    r"""The document's language: `\setmainlanguage{english}`."""

    cs = "setmainlanguage"
    options: LanguageOptions | None = arg(SQUARE, default=None)
    language: Name


@package.command
class SetOtherLanguage(Command):
    r"""A further language the document uses: `\setotherlanguage{german}`."""

    cs = "setotherlanguage"
    options: LanguageOptions | None = arg(SQUARE, default=None)
    language: Name
