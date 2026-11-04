r"""microtype: Micro-typography.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package. The keys
are the ones microtype documents; `extra` takes any other, as written."""

import dataclasses
import enum

from texmodel.components import Command
from texmodel.interface import SQUARE, Flag, Item, Star, Switch, arg
from texmodel.keys import KEYVAL
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import AsTeX, Choice, Length, NameList, Raw, Text

package = Package("microtype", prefix="", adopted=True)


@enum.unique
class Compatibility(Choice):
    """How far protrusion and expansion keep to the font's compatibility settings (`protrusion=compatibility`)."""

    COMPATIBILITY = "compatibility"
    NOCOMPATIBILITY = "nocompatibility"


@enum.unique
class Verbosity(Choice):
    """What microtype reports besides `true` and `false`."""

    ERRORS = "errors"
    SILENT = "silent"


@enum.unique
class DisableWhen(Choice):
    """`disable=ifdraft`: switch microtype off in a draft."""

    IF_DRAFT = "ifdraft"


@enum.unique
class Patches(Choice):
    """`patch=none`, `nopatch=all`; a list of patches is a `NameList`."""

    ALL = "all"
    NONE = "none"


@enum.unique
class Character(Choice):
    """`unit=character`: relative to the width of each character (the default of protrusion)."""

    CHARACTER = "character"


@enum.unique
class Everything(Choice):
    """`*`: every encoding, family, series or shape."""

    ALL = Raw("*")


@enum.unique
class Feature(Choice):
    """A feature a set belongs to."""

    PROTRUSION = "protrusion"
    EXPANSION = "expansion"
    SPACING = "spacing"
    KERNING = "kerning"
    TRACKING = "tracking"


Selection = Everything | Text  # `*`, or a comma-separated list of names


class MicrotypeOptions(KeyVals, rules=KEYVAL):
    r"""The keys of the package options and of `\microtypesetup` in the preamble: `MicrotypeOptions(protrusion=True,
    stretch=20)`. A feature (`protrusion`, ...) takes `True`, `False`, a `Compatibility` or the `Text` name of a
    declared set; `spacing` and `kerning` need an engine that has them (`pdftex`)."""

    protrusion: bool | Compatibility | Text | None = None
    expansion: bool | Compatibility | Text | None = None
    activate: bool | Compatibility | None = None
    spacing: bool | Text | None = None
    kerning: bool | Text | None = None
    tracking: bool | Text | None = None
    final: Switch | None = None
    draft: Switch | None = None
    selected: Switch | None = None
    babel: Switch | None = None
    auto: Switch | None = None
    defersetup: Switch | None = None
    disable: bool | DisableWhen | None = None
    verbose: bool | Verbosity | None = None
    factor: int | None = None
    stretch: int | None = None
    shrink: int | None = None
    step: int | None = None
    letterspace: int | None = None
    unit: Length | Character | None = None
    patch: Patches | NameList | None = None
    nopatch: Patches | NameList | None = None
    config: Text | None = None
    extra: Item[Raw] | None = None


class DocumentOptions(KeyVals, rules=KEYVAL):
    r"""The keys `\microtypesetup` takes once the preamble is over, a subset of `MicrotypeOptions`, and the two flags
    `deactivate` and `reactivate`: `DocumentOptions(deactivate=True)`. A feature the package options disabled stays off.
    """

    protrusion: bool | Compatibility | Text | None = None
    expansion: bool | Compatibility | Text | None = None
    activate: bool | Compatibility | None = None
    spacing: bool | Text | None = None
    kerning: bool | Text | None = None
    tracking: bool | Text | None = None
    patch: Patches | NameList | None = None
    nopatch: Patches | NameList | None = None
    deactivate: Flag = False
    reactivate: Flag = False
    extra: Item[Raw] | None = None


class FontSet(KeyVals, rules=KEYVAL):
    r"""The fonts a setting applies to: `FontSet(encoding=Everything.ALL)` is `encoding=*`, `FontSet(family="cmr,ptm")`
    two families. `size` is a range (`8-10`) and `font` the NFSS tuple `encoding/family/series/shape/size`."""

    encoding: Selection | None = None
    family: Selection | None = None
    series: Selection | None = None
    shape: Selection | None = None
    size: Text | None = None
    font: Selection | None = None
    extra: Item[Raw] | None = None


class SettingOptions(KeyVals, rules=KEYVAL):
    r"""The keys every list of settings takes (`\SetProtrusion[name=tm]{...}{...}`)."""

    name: Text | None = None
    load: Text | None = None
    factor: int | None = None
    preset: Text | None = None
    inputenc: Text | None = None
    context: Text | None = None
    extra: Item[Raw] | None = None


class ProtrusionOptions(SettingOptions, rules=KEYVAL):
    r"""The keys of `\SetProtrusion`: those of every list, and `unit`."""

    unit: Length | Character | None = None


class TrackingOptions(SettingOptions, rules=KEYVAL):
    r"""The keys of `\SetTracking`: those of every list, and `unit`. Others (`spacing`, `outer spacing`, `no ligatures`)
    go in `extra`."""

    unit: Length | None = None


class ContextKeys(KeyVals, rules=KEYVAL):
    r"""The keys of `\microtypecontext`: the context each feature uses from here: `ContextKeys(spacing="nonfrench")`."""

    protrusion: Text | None = None
    expansion: Text | None = None
    spacing: Text | None = None
    kerning: Text | None = None
    tracking: Text | None = None
    activate: Text | None = None
    extra: Item[Raw] | None = None


def _chars(chars: tuple[str, ...]) -> str:
    if not chars or any(not c or set(c) & set(",={}") for c in chars):
        raise ValueError(f"characters {chars!r}: give them as strings with none of `,={{}}`")
    return chars[0] if len(chars) == 1 else "{" + ",".join(chars) + "}"


@dataclasses.dataclass(frozen=True)
class Sides(AsTeX):
    r"""Amounts, in thousandths of the unit, on the left and the right of some characters (protrusion, extra kerning,
    extra spacing): `Sides(("A",), 50, 50)` is `A={50,50}`, `Sides(("A", "V"), right=30)` is `{A,V}={,30}`."""

    chars: tuple[str, ...]
    left: int | None = None
    right: int | None = None

    def __post_init__(self) -> None:
        _chars(self.chars)
        if self.left is None and self.right is None:
            raise ValueError(f"{self.chars!r}: give a left or a right amount")

    def render(self) -> str:
        left, right = ("" if x is None else str(x) for x in (self.left, self.right))
        return f"{_chars(self.chars)}={{{left},{right}}}"


@dataclasses.dataclass(frozen=True)
class Weight(AsTeX):
    r"""An amount for some characters (expansion): `Weight(("A",), 1000)` is `A=1000`."""

    chars: tuple[str, ...]
    amount: int

    def __post_init__(self) -> None:
        _chars(self.chars)

    def render(self) -> str:
        return f"{_chars(self.chars)}={self.amount}"


@package.command
class MicrotypeSetup(Command):
    r"""Change microtype's options after loading: `\microtypesetup{protrusion=true}`. In the preamble it takes
    `MicrotypeOptions`; in the document, `DocumentOptions`."""

    cs = "microtypesetup"
    options: MicrotypeOptions | DocumentOptions


@package.command
class SetProtrusion(Command):
    r"""Protrusion of characters: `\SetProtrusion[name=x]{encoding=*}{A={50,50}}`."""

    cs = "SetProtrusion"
    options: ProtrusionOptions | None = arg(SQUARE, default=None)
    fonts: FontSet
    values: list[Sides]


@package.command
class SetExpansion(Command):
    r"""Font expansion of characters: `\SetExpansion[name=x]{encoding=*}{A=1000}`."""

    cs = "SetExpansion"
    options: SettingOptions | None = arg(SQUARE, default=None)
    fonts: FontSet
    values: list[Weight]


@package.command
class SetTracking(Command):
    r"""Tracking (letterspacing) in thousandths of an em, for the fonts: `\SetTracking[name=x]{encoding=*}{50}`."""

    cs = "SetTracking"
    options: TrackingOptions | None = arg(SQUARE, default=None)
    fonts: FontSet
    amount: int


@package.command
class SetExtraKerning(Command):
    r"""Extra kerning next to characters: `\SetExtraKerning[name=x]{encoding=*}{A={50,50}}`."""

    cs = "SetExtraKerning"
    options: SettingOptions | None = arg(SQUARE, default=None)
    fonts: FontSet
    values: list[Sides]


@package.command
class SetExtraSpacing(Command):
    r"""Extra interword spacing next to characters: `\SetExtraSpacing[name=x]{encoding=*}{A={50,50}}`."""

    cs = "SetExtraSpacing"
    options: SettingOptions | None = arg(SQUARE, default=None)
    fonts: FontSet
    values: list[Sides]


@package.command
class DisableLigatures(Command):
    r"""Disable ligatures for fonts, in the preamble: `\DisableLigatures[f]{encoding=*,family=*}`; `ligatures` are the
    letters they start with (all, when unset)."""

    cs = "DisableLigatures"
    ligatures: list[Text] | None = arg(SQUARE, default=None)
    fonts: FontSet


@package.command
class DeclareMicrotypeSet(Command):
    r"""Name a selection of fonts, in the preamble: `\DeclareMicrotypeSet[protrusion]{caps}{encoding=*}`."""

    cs = "DeclareMicrotypeSet"
    features: list[Feature] | None = arg(SQUARE, default=None)
    name: Text
    fonts: FontSet


@package.command
class UseMicrotypeSet(Command):
    r"""Use a named set for features, in the preamble: `\UseMicrotypeSet[protrusion]{caps}`."""

    cs = "UseMicrotypeSet"
    features: list[Feature] | None = arg(SQUARE, default=None)
    name: Text


@package.command
class DeclareMicrotypeSetDefault(Command):
    r"""Make a set the default for features, in the preamble: `\DeclareMicrotypeSetDefault[protrusion]{caps}`."""

    cs = "DeclareMicrotypeSetDefault"
    features: list[Feature] | None = arg(SQUARE, default=None)
    name: Text


@package.command
class DeclareMicrotypeAlias(Command):
    r"""Treat a font as another for the settings: `\DeclareMicrotypeAlias{Fira}{cmr}`."""

    cs = "DeclareMicrotypeAlias"
    font: Text
    alias: Text


@package.command
class DeclareMicrotypeVariants(Command):
    r"""The shape variants the settings also cover, in the preamble: `\DeclareMicrotypeVariants{sc,sl}`."""

    cs = "DeclareMicrotypeVariants"
    variants: NameList


@package.command
class MicrotypeContext(Command):
    r"""Switch the settings' context from here: `\microtypecontext{spacing=nonfrench}`."""

    cs = "microtypecontext"
    keys: ContextKeys


@package.command
class TextMicrotypeContext(Command):
    r"""A text in another settings context: `\textmicrotypecontext{spacing=nonfrench}{text}`."""

    cs = "textmicrotypecontext"
    keys: ContextKeys
    text: Raw  # content


@package.command
class LeftProtrusion(Command):
    r"""Protrude the text's first character as the font settings say: `\leftprotrusion{text}`."""

    cs = "leftprotrusion"
    text: Raw  # content


@package.command
class RightProtrusion(Command):
    r"""Protrude the text's last character as the font settings say: `\rightprotrusion{text}`."""

    cs = "rightprotrusion"
    text: Raw  # content


@package.command
class NoProtrusion(Command):
    r"""Stop the character before it from protruding."""

    cs = "noprotrusion"


@package.command
class LetterSpaceStyle(Command):
    r"""Letterspace the rest of the group (by `\textls`'s amount or the tracking set)."""

    cs = "lsstyle"


@package.command
class TextLetterSpace(Command):
    r"""Letterspaced text: `\textls{text}`, `\textls[100]{text}` (thousandths of an em), `\textls*{text}` (keeps the
    spacing at the ends)."""

    cs = "textls"
    starred: Star = arg(default=False)
    amount: int | None = arg(SQUARE, default=None)
    text: Raw  # content
