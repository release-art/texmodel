r"""graphicx: Pictures: `\includegraphics` and where to look for them.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

import dataclasses

from texmodel.components import Command
from texmodel.interface import Flag, Item
from texmodel.keys import KEYVAL
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import AsTeX, FilePath, Length, Macro, Raw, Text

package = Package("graphicx", prefix="", adopted=True)


@dataclasses.dataclass(frozen=True)
class Trim(AsTeX):
    """What `trim` cuts off each edge of a picture: `Trim(left=Length("1cm"), top=Length("2mm"))` is `1cm 0pt 0pt 2mm`
    (left, bottom, right, top; an edge left out cuts nothing)."""

    left: Length = Length("0pt")
    bottom: Length = Length("0pt")
    right: Length = Length("0pt")
    top: Length = Length("0pt")

    def render(self) -> str:
        return f"{self.left} {self.bottom} {self.right} {self.top}"


@dataclasses.dataclass(frozen=True)
class Directories(AsTeX):
    r"""The directories of `\graphicspath`, each in its own group: `Directories((FilePath("img/"),))` is `{img/}`. The
    empty path, `FilePath` cannot be empty, is `include_cwd`: the current directory first."""

    dirs: tuple[FilePath, ...]
    include_cwd: bool = True

    def render(self) -> str:
        return ("{}" if self.include_cwd else "") + "".join(f"{{{d.tex}}}" for d in self.dirs)


class IncludeGraphicsOptions(KeyVals, rules=KEYVAL):
    r"""The keys of `\includegraphics` (graphicx reads them with `keyval`):
    `IncludeGraphicsOptions(width=Length("3cm"))`."""

    width: Length | None = None
    height: Length | None = None
    totalheight: Length | None = None
    keepaspectratio: Flag = False
    scale: float | None = None
    angle: float | None = None
    page: int | None = None
    clip: Flag = False
    draft: Flag = False
    trim: Trim | None = None  # cut off when `clip` is set
    alt: Text | None = None  # the text for a tagged PDF (LaTeX 2024-11 and later)
    artifact: Flag = False  # a picture that is decoration, which a tagged PDF leaves out
    extra: Item[Raw] | None = None


@package.command
class IncludeGraphics(Command):
    r"""Place a picture: `\includegraphics[width=3cm]{a.png}`. `path` is a `FilePath` (a checked
    file name) or a `Macro` (`\figdir{a}`, or a bare `ControlSequence`) that expands to it."""

    cs = "includegraphics"
    path: FilePath | Macro
    options: IncludeGraphicsOptions | None = None


@package.command
class GraphicsPath(Command):
    r"""Directories searched for pictures; the first group `{}` keeps the current one."""

    cs = "graphicspath"
    directories: Directories
