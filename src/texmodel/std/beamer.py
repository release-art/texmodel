r"""beamer: Presentations.

A header (the class is adopted): it declares the interface, `texmodel` writes calls and never the class. The package
that builds the deck is `Package(..., document_class="beamer")`. An overlay specification (`<2->`) is a `Text` field
named `overlay`, written in angle brackets before the other arguments."""

import enum

from texmodel.components import Anywhere, ColourRef, Command, Environment, Passthrough
from texmodel.interface import ANGLE, BRACE, SQUARE, Flag, Gap, Item, arg
from texmodel.keys import KEYVAL
from texmodel.keyvals import KeyVals, key
from texmodel.package import Package
from texmodel.types import Choice, Length, Macro, Name, NameList, Raw, Text

package = Package("beamer", prefix="", adopted=True, builtin=True, document_class="beamer")


@enum.unique
class Align(Choice):
    """Where a frame's or a column's content sits: `t` top, `c` centre, `b` bottom, `T` top by the first line."""

    TOP = "t"
    CENTRE = "c"
    BOTTOM = "b"
    TOP_BY_FIRST_LINE = "T"


@enum.unique
class Option(Choice):
    r"""`\setbeameroption`: whether the notes are typeset."""

    HIDE_NOTES = "hide notes"
    SHOW_NOTES = "show notes"
    SHOW_ONLY_NOTES = "show only notes"


# --- frames ------------------------------------------------------------------------------------------------------


class FrameOptions(KeyVals, rules=KEYVAL):
    r"""The options of a frame: `FrameOptions(t=True, fragile=True)`. Other keys go in `extra`."""

    t: Flag = False
    c: Flag = False
    b: Flag = False
    plain: Flag = False
    fragile: Flag = False
    allowframebreaks: Flag = False
    squeeze: Flag = False
    noframenumbering: Flag = False
    shrink: int | None = None
    label: Name | None = None
    extra: Item[Raw] | None = None


@package.environment
class Frame(Environment):
    r"""A slide: `\begin{frame}[t]{Title}{Subtitle}`. A subtitle needs a title."""

    cs = "frame"
    children = [Anywhere(Passthrough)]
    overlay: Text | None = arg(ANGLE, default=None, fill=Gap.OMIT)
    options: FrameOptions | None = arg(SQUARE, default=None, fill=Gap.OMIT)
    title: Text | None = arg(BRACE, default=None, fill="")
    subtitle: Text | None = arg(BRACE, default=None)


@package.command
class FrameTitle(Command):
    r"""The title of the frame, set inside it: `\frametitle<2>[Short]{Title}`."""

    cs = "frametitle"
    overlay: Text | None = arg(ANGLE, default=None, fill=Gap.OMIT)
    short: Text | None = arg(SQUARE, default=None)
    title: Text


@package.command
class FrameSubtitle(Command):
    r"""The subtitle of the frame: `\framesubtitle{Subtitle}`."""

    cs = "framesubtitle"
    overlay: Text | None = arg(ANGLE, default=None)
    subtitle: Text


@package.command
class FrameBreak(Command):
    r"""Continue on the next slide, in a frame with `allowframebreaks`."""

    cs = "framebreak"


@package.command
class AgainFrame(Command):
    r"""Show the frame labelled `label` again: `\againframe<2->[plain]{label}`."""

    cs = "againframe"
    overlay: Text | None = arg(ANGLE, default=None, fill=Gap.OMIT)
    options: FrameOptions | None = arg(SQUARE, default=None)
    label: Name


# --- the title page and the outline -------------------------------------------------------------------------------


@package.command
class Title(Command):
    r"""The title; `short` is what the footer shows: `\title[Short]{Title}`."""

    cs = "title"
    short: Text | None = arg(SQUARE, default=None)
    title: Text


@package.command
class Subtitle(Command):
    r"""The subtitle, as `Title`."""

    cs = "subtitle"
    short: Text | None = arg(SQUARE, default=None)
    subtitle: Text


@package.command
class Author(Command):
    r"""The authors, as `Title`."""

    cs = "author"
    short: Text | None = arg(SQUARE, default=None)
    authors: Text


@package.command
class Institute(Command):
    r"""The institute, as `Title`."""

    cs = "institute"
    short: Text | None = arg(SQUARE, default=None)
    institute: Text


@package.command
class Date(Command):
    r"""The date, as `Title`."""

    cs = "date"
    short: Text | None = arg(SQUARE, default=None)
    date: Text


@package.command
class TitleGraphic(Command):
    r"""A picture on the title page."""

    cs = "titlegraphic"
    graphic: Raw


@package.command
class TitlePage(Command):
    r"""The title page, in a frame."""

    cs = "titlepage"


class ContentsOptions(KeyVals, rules=KEYVAL):
    r"""The options of `\tableofcontents`; other keys go in `extra`."""

    currentsection: Flag = False
    currentsubsection: Flag = False
    hideallsubsections: Flag = False
    hideothersubsections: Flag = False
    sections: Text | None = None
    pausesections: Flag = False
    pausesubsections: Flag = False
    subsectionstyle: Text | None = None
    sectionstyle: Text | None = None
    extra: Item[Raw] | None = None


@package.command
class TableOfContents(Command):
    r"""The outline: `\tableofcontents[currentsection]`."""

    cs = "tableofcontents"
    options: ContentsOptions | None = None


@package.command
class AtBeginSection(Command):
    r"""Code run at the start of each section; `star` is the code for an unnumbered one."""

    cs = "AtBeginSection"
    star: Raw | None = arg(SQUARE, default=None)
    code: Raw


@package.command
class AtBeginSubsection(Command):
    r"""Code run at the start of each subsection, as `AtBeginSection`."""

    cs = "AtBeginSubsection"
    star: Raw | None = arg(SQUARE, default=None)
    code: Raw


# --- blocks and columns -------------------------------------------------------------------------------------------


@package.environment
class Block(Environment):
    r"""A titled block: `\begin{block}{Title}`."""

    cs = "block"
    children = [Anywhere(Passthrough)]
    overlay: Text | None = arg(ANGLE, default=None)
    title: Text


@package.environment
class AlertBlock(Environment):
    r"""A block in the alert colours, as `Block`."""

    cs = "alertblock"
    children = [Anywhere(Passthrough)]
    overlay: Text | None = arg(ANGLE, default=None)
    title: Text


@package.environment
class ExampleBlock(Environment):
    r"""A block in the example colours, as `Block`."""

    cs = "exampleblock"
    children = [Anywhere(Passthrough)]
    overlay: Text | None = arg(ANGLE, default=None)
    title: Text


@package.environment
class Column(Environment):
    r"""A column of `Columns`: `\begin{column}[t]{0.5\textwidth}`."""

    cs = "column"
    children = [Anywhere(Passthrough)]
    align: Align | None = None
    width: Length


class ColumnsOptions(KeyVals, rules=KEYVAL):
    r"""The options of `Columns`: `ColumnsOptions(onlytextwidth=True)`; other keys go in `extra`."""

    t: Flag = False
    c: Flag = False
    b: Flag = False
    top_by_first_line: Flag = key("T", default=False)
    onlytextwidth: Flag = False
    flushleft: Flag = False
    totalwidth: Length | None = None
    extra: Item[Raw] | None = None


@package.environment
class Columns(Environment):
    r"""Columns side by side: `\begin{columns}[onlytextwidth]`."""

    cs = "columns"
    children = [Anywhere(Passthrough), Anywhere(Column)]
    options: ColumnsOptions | None = None


# --- overlays ----------------------------------------------------------------------------------------------------


@package.command
class Pause(Command):
    r"""Show what follows on the next slide; `\pause[3]` resumes at slide 3."""

    cs = "pause"
    slide: int | None = None


@package.command
class Only(Command):
    r"""Typeset the text on the slides of the overlay only: `\only<2>{text}`."""

    cs = "only"
    overlay: Text = arg(ANGLE)
    text: Raw


@package.command
class Onslide(Command):
    r"""Show what follows (or `text`) on the slides of the overlay: `\onslide<2->`."""

    cs = "onslide"
    overlay: Text = arg(ANGLE)
    text: Raw | None = arg(BRACE, default=None)


@package.command
class Uncover(Command):
    r"""Reserve the space of the text and show it on the slides of the overlay."""

    cs = "uncover"
    overlay: Text = arg(ANGLE)
    text: Raw


@package.command
class Visible(Command):
    r"""Show the text on the slides of the overlay and keep its space, as `Uncover`."""

    cs = "visible"
    overlay: Text = arg(ANGLE)
    text: Raw


@package.command
class Invisible(Command):
    r"""Hide the text on the slides of the overlay, keeping its space."""

    cs = "invisible"
    overlay: Text = arg(ANGLE)
    text: Raw


@package.command
class Alert(Command):
    r"""Emphasize the text, on the slides of the overlay if one is given: `\alert<2>{text}`."""

    cs = "alert"
    overlay: Text | None = arg(ANGLE, default=None)
    text: Raw


@package.command
class Alt(Command):
    r"""One text on the slides of the overlay, another on the rest: `\alt<2>{this}{that}`."""

    cs = "alt"
    overlay: Text = arg(ANGLE)
    this: Raw
    that: Raw


@package.command
class Temporal(Command):
    r"""A text before, during and after the overlay: `\temporal<2-3>{before}{during}{after}`."""

    cs = "temporal"
    overlay: Text = arg(ANGLE)
    before: Raw
    during: Raw
    after: Raw


@package.command
class ItemOn(Command):
    r"""A list item shown on the slides of the overlay: `\item<2->[label]`."""

    cs = "item"
    overlay: Text | None = arg(ANGLE, default=None, fill=Gap.OMIT)
    label: Text | None = arg(SQUARE, default=None)


@package.environment
class OnlyEnv(Environment):
    r"""The environment form of `Only`."""

    cs = "onlyenv"
    children = [Anywhere(Passthrough)]
    overlay: Text = arg(ANGLE)


@package.environment
class UncoverEnv(Environment):
    r"""The environment form of `Uncover`."""

    cs = "uncoverenv"
    children = [Anywhere(Passthrough)]
    overlay: Text = arg(ANGLE)


@package.environment
class VisibleEnv(Environment):
    r"""The environment form of `Visible`."""

    cs = "visibleenv"
    children = [Anywhere(Passthrough)]
    overlay: Text = arg(ANGLE)


@package.environment
class InvisibleEnv(Environment):
    r"""The environment form of `Invisible`."""

    cs = "invisibleenv"
    children = [Anywhere(Passthrough)]
    overlay: Text = arg(ANGLE)


@package.environment
class AlertEnv(Environment):
    r"""The environment form of `Alert`."""

    cs = "alertenv"
    children = [Anywhere(Passthrough)]
    overlay: Text = arg(ANGLE)


@package.environment
class Overprint(Environment):
    r"""Slides in the same place: `\begin{overprint}[\textwidth]` with an `Onslide` between them."""

    cs = "overprint"
    children = [Anywhere(Passthrough)]
    width: Length | None = None


# --- notes -------------------------------------------------------------------------------------------------------


@package.command
class Note(Command):
    r"""A note on the slide: `\note[item]{text}`; the note pages show it."""

    cs = "note"
    overlay: Text | None = arg(ANGLE, default=None, fill=Gap.OMIT)
    options: Text | None = arg(SQUARE, default=None)
    text: Raw


# --- themes and templates --------------------------------------------------------------------------------------------


@package.command
class UseTheme(Command):
    r"""The presentation theme: `\usetheme[secheader]{Madrid}`."""

    cs = "usetheme"
    options: Text | None = None
    name: Name


@package.command
class UseColorTheme(Command):
    r"""The colour theme: `\usecolortheme{beaver}`."""

    cs = "usecolortheme"
    options: Text | None = None
    name: NameList


@package.command
class UseFontTheme(Command):
    r"""The font theme: `\usefonttheme{professionalfonts}`."""

    cs = "usefonttheme"
    options: Text | None = None
    name: NameList


@package.command
class UseInnerTheme(Command):
    r"""The inner theme (frame titles, blocks, lists): `\useinnertheme{rounded}`."""

    cs = "useinnertheme"
    options: Text | None = None
    name: NameList


@package.command
class UseOuterTheme(Command):
    r"""The outer theme (headline, footline, sidebars): `\useoutertheme{infolines}`."""

    cs = "useoutertheme"
    options: Text | None = None
    name: NameList


class ColorOptions(KeyVals, rules=KEYVAL):
    r"""What `\setbeamercolor` sets: `ColorOptions(fg=ColourName("white"), bg=ColourName("black"))`."""

    fg: ColourRef | None = None
    bg: ColourRef | None = None
    parent: Text | None = None
    use: Text | None = None
    extra: Item[Raw] | None = None


@package.command
class SetBeamerColor(Command):
    r"""Colour an element: `\setbeamercolor{block title}{fg=white,bg=black}`."""

    cs = "setbeamercolor"
    element: Text
    options: ColorOptions


class FontOptions(KeyVals, rules=KEYVAL):
    r"""What `\setbeamerfont` sets; a value is a font command (`Macro(r"\bfseries")`)."""

    family: Macro | None = None
    series: Macro | None = None
    shape: Macro | None = None
    size: Macro | None = None
    parent: Text | None = None
    extra: Item[Raw] | None = None


@package.command
class SetBeamerFont(Command):
    r"""Set the font of an element: `\setbeamerfont{frametitle}{series=\bfseries}`."""

    cs = "setbeamerfont"
    element: Text
    options: FontOptions


@package.command
class SetBeamerTemplate(Command):
    r"""Set the template of an element, to a named style or to code: `\setbeamertemplate{items}[circle]`,
    `\setbeamertemplate{navigation symbols}{}`."""

    cs = "setbeamertemplate"
    element: Text
    style: Text | None = arg(SQUARE, default=None, fill=Gap.OMIT)
    code: Raw | None = arg(BRACE, default=None)


class SizeOptions(KeyVals, rules=KEYVAL):
    r"""What `\setbeamersize` sets; other keys go in `extra`."""

    text_margin_left: Length | None = key("text margin left", default=None)
    text_margin_right: Length | None = key("text margin right", default=None)
    sidebar_width_left: Length | None = key("sidebar width left", default=None)
    sidebar_width_right: Length | None = key("sidebar width right", default=None)
    description_width: Length | None = key("description width", default=None)
    mini_frame_size: Length | None = key("mini frame size", default=None)
    extra: Item[Raw] | None = None


@package.command
class SetBeamerSize(Command):
    r"""Set a size: `\setbeamersize{text margin left=1cm}`."""

    cs = "setbeamersize"
    options: SizeOptions


@package.command
class SetBeamerOption(Command):
    r"""Set a beamer option: `\setbeameroption{show notes}`."""

    cs = "setbeameroption"
    option: Option


@package.command
class UseBackgroundTemplate(Command):
    r"""What is drawn behind every slide."""

    cs = "usebackgroundtemplate"
    code: Raw


@package.command
class Logo(Command):
    r"""A logo on every slide."""

    cs = "logo"
    graphic: Raw
