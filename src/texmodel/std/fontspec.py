r"""fontspec: System fonts under LuaLaTeX and XeLaTeX.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package. To run a
call when a package loads, give it to `Package.at_load`."""

import enum

from texmodel.components import Command
from texmodel.interface import SQUARE, Item, arg
from texmodel.keys import XKEYVAL
from texmodel.keyvals import KeyVals, key
from texmodel.package import Package
from texmodel.types import Choice, ControlSequence, FontName, Raw, Text

package = Package("fontspec", prefix="", adopted=True)


@enum.unique
class Ligature(Choice):
    """A value of `Ligatures`; `TeX` turns `--`, `---` and quotes into their characters."""

    COMMON = "Common"
    NO_COMMON = "NoCommon"
    RARE = "Rare"
    NO_RARE = "NoRare"
    DISCRETIONARY = "Discretionary"
    NO_DISCRETIONARY = "NoDiscretionary"
    HISTORIC = "Historic"
    NO_HISTORIC = "NoHistoric"
    CONTEXTUAL = "Contextual"
    NO_CONTEXTUAL = "NoContextual"
    TEX = "TeX"
    RESET = "ResetAll"


@enum.unique
class Number(Choice):
    """A value of `Numbers`."""

    LINING = "Lining"
    OLD_STYLE = "OldStyle"
    PROPORTIONAL = "Proportional"
    MONOSPACED = "Monospaced"
    SLASHED_ZERO = "SlashedZero"
    NO_SLASHED_ZERO = "NoSlashedZero"
    UPPERCASE = "Uppercase"


@enum.unique
class Letter(Choice):
    """A value of `Letters`."""

    SMALL_CAPS = "SmallCaps"
    UPPERCASE_SMALL_CAPS = "UppercaseSmallCaps"
    PETITE_CAPS = "PetiteCaps"
    UPPERCASE_PETITE_CAPS = "UppercasePetiteCaps"
    UNICASE = "Unicase"
    UPPERCASE = "Uppercase"
    LOWERCASE = "Lowercase"


@enum.unique
class Scaling(Choice):
    """`Scale=MatchLowercase`: size the font so its x-height (or cap height) matches the main font's."""

    MATCH_LOWERCASE = "MatchLowercase"
    MATCH_UPPERCASE = "MatchUppercase"


@enum.unique
class Kerning(Choice):
    """A value of `Kerning`."""

    ON = "On"
    OFF = "Off"
    UPPERCASE = "Uppercase"


@enum.unique
class Renderer(Choice):
    """A value of `Renderer` (LuaLaTeX has `Harfbuzz`, XeLaTeX `Graphite`, `ICU` and `AAT`)."""

    BASIC = "Basic"
    HARFBUZZ = "Harfbuzz"
    OPENTYPE = "OpenType"
    ICU = "ICU"
    GRAPHITE = "Graphite"
    AAT = "AAT"


class FontOptions(KeyVals, rules=XKEYVAL):
    r"""The options of a font: `FontOptions(bold_font=FontName("Skolar-Bold.otf"), ligatures=[Ligature.COMMON])`. The
    files of the other faces are looked up under `path` and `extension`. `extra` takes the rest, as written
    (`RawFeature=+salt`, `BoldFeatures={Color=ff0000}`)."""

    path: Text | None = key("Path")
    extension: Text | None = key("Extension")
    upright_font: FontName | None = key("UprightFont")
    italic_font: FontName | None = key("ItalicFont")
    bold_font: FontName | None = key("BoldFont")
    bold_italic_font: FontName | None = key("BoldItalicFont")
    slanted_font: FontName | None = key("SlantedFont")
    bold_slanted_font: FontName | None = key("BoldSlantedFont")
    small_caps_font: FontName | None = key("SmallCapsFont")
    scale: float | Scaling | None = key("Scale")
    color: Text | None = key("Color")
    ligatures: tuple[Ligature, ...] | None = key("Ligatures")
    numbers: tuple[Number, ...] | None = key("Numbers")
    letters: tuple[Letter, ...] | None = key("Letters")
    kerning: Kerning | None = key("Kerning")
    stylistic_set: tuple[int, ...] | None = key("StylisticSet")
    character_variant: tuple[int, ...] | None = key("CharacterVariant")
    language: Text | None = key("Language")
    script: Text | None = key("Script")
    renderer: Renderer | None = key("Renderer")
    optical_size: float | None = key("OpticalSize")
    letter_space: float | None = key("LetterSpace")
    fake_bold: float | None = key("FakeBold")
    fake_slant: float | None = key("FakeSlant")
    mapping: Text | None = key("Mapping")
    extra: Item[Raw] | None = None


@package.command
class SetMainFont(Command):
    r"""The main font: `\setmainfont[Path=fonts/]{Nunito-Regular.ttf}`."""

    cs = "setmainfont"
    font: FontName
    options: FontOptions | None = None


@package.command
class SetSansFont(Command):
    r"""The sans-serif font."""

    cs = "setsansfont"
    font: FontName
    options: FontOptions | None = None


@package.command
class SetMonoFont(Command):
    r"""The monospaced font."""

    cs = "setmonofont"
    font: FontName
    options: FontOptions | None = None


@package.command
class NewFontFamily(Command):
    r"""Define a command that switches to a font family: `\newfontfamily\skolar[BoldFont=Skolar-Bold.otf]{Skolar.otf}`.
    The command is defined where the call is written."""

    cs = "newfontfamily"
    command: ControlSequence
    options: FontOptions | None = arg(SQUARE, default=None)
    font: FontName


@package.command
class NewFontFace(Command):
    r"""Define a command that switches to one face: `\newfontface\skolarbold{Skolar-Bold.otf}`."""

    cs = "newfontface"
    command: ControlSequence
    options: FontOptions | None = arg(SQUARE, default=None)
    font: FontName


@package.command
class FontSpec(Command):
    r"""Switch to a font from here: `\fontspec[Ligatures=Common]{Skolar.otf}`."""

    cs = "fontspec"
    font: FontName
    options: FontOptions | None = None


@package.command
class AddFontFeatures(Command):
    r"""Add features to the current font: `\addfontfeatures{Numbers=OldStyle}`."""

    cs = "addfontfeatures"
    options: FontOptions


@package.command
class DefaultFontFeatures(Command):
    r"""Features for every font defined after this, or for the font `font`: `\defaultfontfeatures[Skolar]{...}`."""

    cs = "defaultfontfeatures"
    font: FontName | None = None
    options: FontOptions
