r"""fontspec: System fonts under LuaLaTeX and XeLaTeX.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import FontName, Raw

package = Package("fontspec", prefix="", adopted=True)


@package.command
class SetMainFont(Command):
    r"""The main font: `\setmainfont[Path=fonts/]{Nunito-Regular.ttf}`."""

    cs = "setmainfont"
    font: FontName
    options: Raw | None = None


@package.command
class SetSansFont(Command):
    r"""The sans-serif font."""

    cs = "setsansfont"
    font: FontName
    options: Raw | None = None


@package.command
class SetMonoFont(Command):
    r"""The monospaced font."""

    cs = "setmonofont"
    font: FontName
    options: Raw | None = None
