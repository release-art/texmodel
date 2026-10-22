r"""latex: The LaTeX kernel: commands every document has without loading a package.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

import enum

from texmodel.components import Anywhere, Command, Environment, Passthrough
from texmodel.interface import SQUARE, Gap, Star, arg
from texmodel.package import Package
from texmodel.types import Choice, Length, Raw, Text

package = Package("latex", prefix="", adopted=True, builtin=True)


@enum.unique
class BoxPosition(Choice):
    """Which line of a box sits on the baseline: the `[t]`, `[c]`, `[b]` of `minipage`."""

    TOP = "t"
    CENTRE = "c"
    BOTTOM = "b"


@enum.unique
class BoxAlign(Choice):
    """How text sits in a `\\makebox`: centred, left, right or spread."""

    CENTRE = "c"
    LEFT = "l"
    RIGHT = "r"
    SPREAD = "s"


@package.command
class MakeBox(Command):
    r"""A box of a given width: `\makebox[3cm][c]{text}`. The alignment needs the width."""

    cs = "makebox"
    width: Length | None = arg(SQUARE, default=None, fill=Gap.REFUSE)
    align: BoxAlign | None = arg(SQUARE, default=None)
    text: Raw


@package.command
class RaiseBox(Command):
    r"""Raise or lower some text: `\raisebox{1pt}[2pt][1pt]{text}`. The depth needs the height."""

    cs = "raisebox"
    lift: Length
    height: Length | None = arg(SQUARE, default=None, fill=Gap.REFUSE)
    depth: Length | None = arg(SQUARE, default=None)
    text: Raw


@package.command
class Section(Command):
    r"""A section heading: `\section{Title}`, `\section*{Title}` (unnumbered), `\section[Short]{Title}` (for the
    table of contents)."""

    cs = "section"
    starred: Star = arg(default=False)
    short: Text | None = arg(SQUARE, default=None)
    title: Text


@package.command
class Subsection(Command):
    r"""A subsection heading, as `Section`."""

    cs = "subsection"
    starred: Star = arg(default=False)
    short: Text | None = arg(SQUARE, default=None)
    title: Text


@package.command
class Subsubsection(Command):
    r"""A subsubsection heading, as `Section`."""

    cs = "subsubsection"
    starred: Star = arg(default=False)
    short: Text | None = arg(SQUARE, default=None)
    title: Text


@package.command
class SetLength(Command):
    r"""Set a length: `\setlength{\parindent}{0pt}`."""

    cs = "setlength"
    length: Raw
    value: Length


@package.command
class AddToLength(Command):
    r"""Add to a length."""

    cs = "addtolength"
    length: Raw
    value: Length


@package.command
class NewLength(Command):
    r"""Declare a length."""

    cs = "newlength"
    length: Raw


@package.command
class SetToWidth(Command):
    r"""Set a length to the width of some text."""

    cs = "settowidth"
    length: Raw
    text: Raw


@package.command
class SetToHeight(Command):
    r"""Set a length to the height of some text."""

    cs = "settoheight"
    length: Raw
    text: Raw


@package.command
class SetToDepth(Command):
    r"""Set a length to the depth of some text."""

    cs = "settodepth"
    length: Raw
    text: Raw


@package.command
class NewCounter(Command):
    r"""Declare a counter."""

    cs = "newcounter"
    name: Raw


@package.command
class SetCounter(Command):
    r"""Set a counter."""

    cs = "setcounter"
    name: Raw
    value: Raw


@package.command
class StepCounter(Command):
    r"""Add one to a counter."""

    cs = "stepcounter"
    name: Raw


@package.command
class Arabic(Command):
    r"""Write a counter in arabic numerals."""

    cs = "arabic"
    name: Raw


@package.command
class CounterValue(Command):
    r"""The value of a counter, for arithmetic."""

    cs = "value"
    name: Raw


@package.command
class VSpace(Command):
    r"""Vertical space: `\vspace{2mm}`, `\vspace*{2mm}` (kept at a page break)."""

    cs = "vspace"
    starred: Star = arg(default=False)
    length: Length


@package.command
class HSpace(Command):
    r"""Horizontal space: `\hspace{2mm}`, `\hspace*{2mm}` (kept at a line break)."""

    cs = "hspace"
    starred: Star = arg(default=False)
    length: Length


@package.command
class NoIndent(Command):
    r"""Start a paragraph without indentation."""

    cs = "noindent"


@package.command
class Par(Command):
    r"""End the paragraph."""

    cs = "par"


@package.command
class ClearPage(Command):
    r"""End the page and flush floats."""

    cs = "clearpage"


@package.command
class NewPage(Command):
    r"""End the page."""

    cs = "newpage"


@package.command
class ThisPageStyle(Command):
    r"""Page style of the current page."""

    cs = "thispagestyle"
    style: Raw


@package.command
class PageStyle(Command):
    r"""Page style from here on."""

    cs = "pagestyle"
    style: Raw


@package.command
class Null(Command):
    r"""An empty box, so a page has content."""

    cs = "null"


@package.command
class IgnoreSpaces(Command):
    r"""Skip the spaces that follow."""

    cs = "ignorespaces"


@package.command
class FrenchSpacing(Command):
    r"""Equal space after every sentence."""

    cs = "frenchspacing"


@package.command
class FontSize(Command):
    r"""Font size and line skip, in effect after `\selectfont`."""

    cs = "fontsize"
    size: Raw
    skip: Raw


@package.command
class SelectFont(Command):
    r"""Apply the font settings made so far."""

    cs = "selectfont"


@package.command
class Bfseries(Command):
    r"""Bold, from here to the end of the group."""

    cs = "bfseries"


@package.command
class Centering(Command):
    r"""Centre the paragraphs of the group."""

    cs = "centering"


@package.command
class Tiny(Command):
    r"""Size `\tiny`."""

    cs = "tiny"


@package.command
class ScriptSize(Command):
    r"""Size `\scriptsize`."""

    cs = "scriptsize"


@package.command
class FootnoteSize(Command):
    r"""Size `\footnotesize`."""

    cs = "footnotesize"


@package.command
class Small(Command):
    r"""Size `\small`."""

    cs = "small"


@package.command
class NormalSize(Command):
    r"""Size `\normalsize`."""

    cs = "normalsize"


@package.command
class Large(Command):
    r"""Size `\large` (lowercase)."""

    cs = "large"


@package.command
class LargeCap(Command):
    r"""Size `\Large`."""

    cs = "Large"


@package.command
class LargeAllCaps(Command):
    r"""Size `\LARGE`."""

    cs = "LARGE"


@package.command
class Huge(Command):
    r"""Size `\huge` (lowercase)."""

    cs = "huge"


@package.command
class HugeCap(Command):
    r"""Size `\Huge`."""

    cs = "Huge"


@package.command
class TextBold(Command):
    r"""Bold text."""

    cs = "textbf"
    text: Text


@package.command
class TextItalic(Command):
    r"""Italic text."""

    cs = "textit"
    text: Text


@package.command
class Emph(Command):
    r"""Emphasised text."""

    cs = "emph"
    text: Text


@package.command
class MakeUppercase(Command):
    r"""Upper-case text."""

    cs = "MakeUppercase"
    text: Text


@package.command
class FpEval(Command):
    r"""A floating-point expression, evaluated where it expands: `\fpeval{round(3*2.5, 1)}`."""

    cs = "fpeval"
    expr: Raw


@package.command
class Phantom(Command):
    r"""Space the size of the text, with nothing in it."""

    cs = "phantom"
    text: Raw


@package.command
class VPhantom(Command):
    r"""Vertical space the size of the text."""

    cs = "vphantom"
    text: Raw


@package.command
class TextBullet(Command):
    r"""A bullet."""

    cs = "textbullet"


@package.command
class TextQuoteLeft(Command):
    r"""A left single quote."""

    cs = "textquoteleft"


@package.command
class TextQuoteRight(Command):
    r"""A right single quote."""

    cs = "textquoteright"


@package.command
class TextQuoteDblLeft(Command):
    r"""A left double quote."""

    cs = "textquotedblleft"


@package.command
class TextQuoteDblRight(Command):
    r"""A right double quote."""

    cs = "textquotedblright"


@package.command
class NewSaveBox(Command):
    r"""Declare a box register."""

    cs = "newsavebox"
    box: Raw


@package.command
class UseBox(Command):
    r"""Typeset a saved box."""

    cs = "usebox"
    box: Raw


@package.command
class AtBeginDocument(Command):
    r"""Run code at `\begin{document}`."""

    cs = "AtBeginDocument"
    code: Raw


@package.command
class AtEndDocument(Command):
    r"""Run code at `\end{document}`."""

    cs = "AtEndDocument"
    code: Raw


@package.command
class PackageError(Command):
    r"""Stop with a package's error."""

    cs = "PackageError"
    package: Raw
    message: Raw
    help: Raw


@package.command
class PackageWarning(Command):
    r"""A package's warning, with the input line."""

    cs = "PackageWarning"
    package: Raw
    message: Raw


@package.command
class PackageWarningNoLine(Command):
    r"""A package's warning, without the input line."""

    cs = "PackageWarningNoLine"
    package: Raw
    message: Raw


@package.command
class PackageInfo(Command):
    r"""A package's note in the log."""

    cs = "PackageInfo"
    package: Raw
    message: Raw


@package.command
class PassOptionsToPackage(Command):
    r"""Options for a package loaded later."""

    cs = "PassOptionsToPackage"
    options: Raw
    package: Raw


@package.command
class DeclareOption(Command):
    r"""Declare a package option and what it does."""

    cs = "DeclareOption"
    option: Raw
    code: Raw


@package.command
class IfFileExists(Command):
    r"""Choose by whether a file can be found."""

    cs = "IfFileExists"
    file: Raw
    yes: Raw
    no: Raw


@package.command
class InputIfFileExists(Command):
    r"""Read a file if it can be found."""

    cs = "InputIfFileExists"
    file: Raw
    yes: Raw
    no: Raw


@package.environment
class Center(Environment):
    r"""Centred paragraphs."""

    cs = "center"
    children = [Anywhere(Passthrough)]


@package.environment
class FlushLeft(Environment):
    r"""Left-aligned paragraphs."""

    cs = "flushleft"
    children = [Anywhere(Passthrough)]


@package.environment
class FlushRight(Environment):
    r"""Right-aligned paragraphs."""

    cs = "flushright"
    children = [Anywhere(Passthrough)]


@package.environment
class Minipage(Environment):
    r"""A box of a given width: `\begin{minipage}[t]{5cm}`."""

    cs = "minipage"
    children = [Anywhere(Passthrough)]
    width: Length
    position: BoxPosition | None = None
