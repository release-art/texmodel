r"""ltx-talk: Presentations that accept `\DocumentMetadata`.

A header (the class is adopted): it declares the interface, `texmodel` writes calls and never the class. The class needs
`\DocumentMetadata`, so every plan has one (empty unless the document says what goes in it). The package
that builds the deck is `Package(..., document_class="ltx-talk")`; its class options are `TalkOptions(...).options()`,
the document's `options`. The class is experimental (TeX Live 2026, ltx-talk 0.4): its template names may move, and
this header is where that shows. Styling is `\EditInstance`, typed per template:
`EditInstance(template=Template.HEADER, instance=Name("std"), keys=HeaderKeys(...))`.

An overlay specification is a `Text` field named `overlay`, written in angle brackets before the other arguments. A
frame's title is its `title` argument (`Frame(..., title="T")`): the package passes the class option `frame-title-arg`,
without which TeX would read the title as text of the frame. `FrameTitle` inside a frame sets it too."""

import dataclasses
import enum
from typing import Any

from texmodel.components import Anywhere, ColourRef, Command, Environment, Passthrough
from texmodel.errors import ValueRuleError, Violation
from texmodel.interface import ANGLE, BRACE, SQUARE, Gap, Item, Switch, arg
from texmodel.keys import KEYVAL
from texmodel.keyvals import KeyVals, key
from texmodel.package import Package
from texmodel.preamble import MetadataPolicy
from texmodel.types import AsTeX, Choice, Length, Name, Raw, Text

package = Package(
    "ltx-talk",
    prefix="",
    adopted=True,
    builtin=True,
    document_class="ltx-talk",
    class_options=("frame-title-arg=true",),  # a frame's title is its `{title}` argument, always written
    metadata=MetadataPolicy.REQUIRED,
)


@enum.unique
class Mode(Choice):
    """`mode`: what the class typesets."""

    PROJECTOR = "projector"
    HANDOUT = "handout"


@enum.unique
class Alignment(Choice):
    """Where a frame's or a title page's content sits."""

    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"
    STRETCH = "stretch"


@enum.unique
class ColumnAlignment(Choice):
    """Where a column sits in its row."""

    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


@enum.unique
class HorizontalAlignment(Choice):
    """Where the title page's elements sit across the page."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


@enum.unique
class FooterElement(Choice):
    """What the footer can show, in the `element_order` of its keys."""

    DATE = "date"
    AUTHOR = "author"
    TITLE = "title"
    SUBTITLE = "subtitle"
    INSTITUTE = "institute"
    FRAME_NUMBER = "framenumber"
    TOTAL_FRAMES = "totalframes"


@enum.unique
class TitleElement(Choice):
    """What the title page shows, in the `element_order` of its keys, and the instances of `TitlePageElementKeys`."""

    TITLE = "title"
    SUBTITLE = "subtitle"
    AUTHOR = "author"
    INSTITUTE = "institute"
    DATE = "date"


# --- the class options -------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class AspectRatio(AsTeX):
    """The shape of a slide: `AspectRatio(16, 9)` is `16:9`."""

    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width < 1 or self.height < 1:
            raise ValueRuleError(
                f"AspectRatio({self.width}, {self.height}): give two whole numbers of 1 or more",
                code="TM-C048",
                hint="AspectRatio(16, 9)",
            )

    def render(self) -> str:
        return f"{self.width}:{self.height}"


class TalkOptions(KeyVals, rules=KEYVAL):
    r"""The class options: `Document(options=TalkOptions(mode=Mode.HANDOUT).options())`."""

    aspect_ratio: AspectRatio | None = key("aspect-ratio", default=None)
    font_size: Length | None = key("font-size", default=None)
    mode: Mode | None = None

    def options(self) -> tuple[str, ...]:
        """The options as a document takes them: `("aspect-ratio=4:3", "mode=handout")`."""
        return tuple(self.render().split(",")) if self.render() else ()


# --- the title page ----------------------------------------------------------------------------------------------


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


class TitlePageKeys(KeyVals, rules=KEYVAL):
    r"""The keys of the title page, for `\maketitle`. `framestyle` is a page style."""

    element_order: tuple[TitleElement, ...] | None = key("element-order", default=None)
    framestyle: Name | None = None
    horizontal_alignment: HorizontalAlignment | None = key("horizontal-alignment", default=None)
    vertical_alignment: Alignment | None = key("vertical-alignment", default=None)


@package.command
class MakeTitle(Command):
    r"""The title page: `\maketitle[horizontal-alignment=left]`. It goes inside a `Frame`: outside one it opens a frame
    of its own, which reads the next token as its title argument."""

    cs = "maketitle"
    options: TitlePageKeys | None = None


# --- frames ------------------------------------------------------------------------------------------------------


class FrameOptions(KeyVals, rules=KEYVAL):
    r"""The options of a frame: `FrameOptions(vertical_alignment=Alignment.TOP)`. Other keys go in `extra`."""

    vertical_alignment: Alignment | None = key("vertical-alignment", default=None)
    extra: Item[Raw] | None = None


@package.environment
class Frame(Environment):
    r"""A slide: `\begin{frame}<2->[vertical-alignment=top]{Title}`. The title argument is always written (`{}` for
    none): the package sets the class option `frame-title-arg`."""

    cs = "frame"
    children = [Anywhere(Passthrough), Anywhere(MakeTitle)]
    overlay: Text | None = arg(ANGLE, default=None, fill=Gap.OMIT)
    options: FrameOptions | None = arg(SQUARE, default=None, fill=Gap.OMIT)
    title: Text = arg(BRACE, default="")


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
    overlay: Text | None = arg(ANGLE, default=None, fill=Gap.OMIT)
    short: Text | None = arg(SQUARE, default=None)
    subtitle: Text


# --- blocks and columns -------------------------------------------------------------------------------------------


@package.environment
class Block(Environment):
    r"""A titled block: `\begin{block}<2>{Title}`."""

    cs = "block"
    children = [Anywhere(Passthrough)]
    overlay: Text | None = arg(ANGLE, default=None)
    title: Text


class ColumnOptions(KeyVals, rules=KEYVAL):
    r"""The options of a column: `ColumnOptions(vertical_alignment=ColumnAlignment.TOP)`."""

    vertical_alignment: ColumnAlignment | None = key("vertical-alignment", default=None)


@package.environment
class Column(Environment):
    r"""A column of `Columns`: `\begin{column}[vertical-alignment=top]{0.5\textwidth}`."""

    cs = "column"
    children = [Anywhere(Passthrough)]
    overlay: Text | None = arg(ANGLE, default=None, fill=Gap.OMIT)
    options: ColumnOptions | None = arg(SQUARE, default=None)
    width: Length


class ColumnsOptions(KeyVals, rules=KEYVAL):
    r"""The options of `Columns`: the row's `width` and the alignment its columns take unless they say."""

    width: Length | None = None
    vertical_alignment: ColumnAlignment | None = key("vertical-alignment", default=None)


@package.environment
class Columns(Environment):
    r"""Columns side by side: `\begin{columns}[width=\textwidth]`."""

    cs = "columns"
    children = [Anywhere(Passthrough), Anywhere(Column)]
    overlay: Text | None = arg(ANGLE, default=None, fill=Gap.OMIT)
    options: ColumnsOptions | None = arg(SQUARE, default=None)


# --- overlays ----------------------------------------------------------------------------------------------------


@package.command
class Pause(Command):
    r"""Show what follows on the next slide."""

    cs = "pause"


@package.command
class Only(Command):
    r"""Typeset the text on the slides of the overlay only: `\only<2>{text}`."""

    cs = "only"
    overlay: Text = arg(ANGLE)
    text: Raw


@package.command
class Onslide(Command):
    r"""Show what follows on the slides of the overlay: `\onslide<2->`."""

    cs = "onslide"
    overlay: Text = arg(ANGLE)


@package.command
class Action(Command):
    r"""Act on the slides of the overlay: `\action<2>{text}`."""

    cs = "action"
    overlay: Text = arg(ANGLE)
    text: Raw


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


@package.environment
class OnlyEnv(Environment):
    r"""The environment form of `Only`."""

    cs = "onlyenv"
    children = [Anywhere(Passthrough)]
    overlay: Text = arg(ANGLE)


@package.environment
class ActionEnv(Environment):
    r"""The environment form of `Action`."""

    cs = "actionenv"
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


# --- styling: \EditInstance ---------------------------------------------------------------------------------------


@enum.unique
class Template(Choice):
    r"""The template types `EditInstance` edits, each with the keys class that fits it."""

    HEADER = "header"
    FOOTER = "footer"
    FRAME_TITLE = "frametitle"
    FOOTER_ELEMENT = "footer-element"
    TITLE_PAGE_ELEMENT = "titlepage-element"


class HeaderKeys(KeyVals, rules=KEYVAL):
    r"""The keys of the `header` template (instances `std`, `wallpaper`). A `font` is TeX: `Raw(r"\small\itshape")`."""

    background_color: ColourRef | None = key("background-color", default=None)
    color: ColourRef | None = None
    font: Raw | None = None
    height: Length | None = None
    left_hspace: Length | None = key("left-hspace", default=None)
    print_frame_title: Switch | None = key("print-frame-title", default=None)
    right_hspace: Length | None = key("right-hspace", default=None)


class FooterKeys(KeyVals, rules=KEYVAL):
    r"""The keys of the `footer` template (instances `std`, `wallpaper`). A `separator` and a `font` are TeX."""

    background_color: ColourRef | None = key("background-color", default=None)
    color: ColourRef | None = None
    element_order: tuple[FooterElement, ...] | None = key("element-order", default=None)
    font: Raw | None = None
    left_hspace: Length | None = key("left-hspace", default=None)
    right_hspace: Length | None = key("right-hspace", default=None)
    separator: Raw | None = None


class FooterElementKeys(KeyVals, rules=KEYVAL):
    r"""The keys of the `footer-element` template; its instances are the `FooterElement`s. A `font` is TeX."""

    color: ColourRef | None = None
    font: Raw | None = None
    left_hspace: Length | None = key("left-hspace", default=None)
    right_hspace: Length | None = key("right-hspace", default=None)


class FrameTitleKeys(KeyVals, rules=KEYVAL):
    r"""The keys of the `frametitle` template (instance `header`). A `font` is TeX."""

    after_vspace: Length | None = key("after-vspace", default=None)
    before_vspace: Length | None = key("before-vspace", default=None)
    color: ColourRef | None = None
    font: Raw | None = None


class TitlePageElementKeys(KeyVals, rules=KEYVAL):
    r"""The keys of the `titlepage-element` template; its instances are the `TitleElement`s. A `font` is TeX."""

    after_skip: Length | None = key("after-skip", default=None)
    before_skip: Length | None = key("before-skip", default=None)
    color: ColourRef | None = None
    font: Raw | None = None


Keys = HeaderKeys | FooterKeys | FooterElementKeys | FrameTitleKeys | TitlePageElementKeys
_KEYS: dict[Template, type[KeyVals]] = {
    Template.HEADER: HeaderKeys,
    Template.FOOTER: FooterKeys,
    Template.FRAME_TITLE: FrameTitleKeys,
    Template.FOOTER_ELEMENT: FooterElementKeys,
    Template.TITLE_PAGE_ELEMENT: TitlePageElementKeys,
}


def _fits(node: Any, path: str) -> list[Violation]:  # noqa: ANN401  # a check is given any node
    expected = _KEYS[node.template]
    if isinstance(node.keys, expected):
        return []
    return [
        Violation(
            "TM-C049",
            f"{path}.keys",
            f"the {node.template.value} template takes {expected.__name__}, not {type(node.keys).__name__}",
            hint=f"keys={expected.__name__}(...)",
        )
    ]


@package.command
class EditInstance(Command):
    r"""Style the class: `\EditInstance{header}{std}{color=white}`. The `keys` class is the template's (`TM-C049`)."""

    cs = "EditInstance"
    checks = [_fits]
    template: Template
    instance: Name
    keys: Keys
