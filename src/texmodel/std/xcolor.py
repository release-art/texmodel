r"""xcolor: Colours.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package. A colour
argument is a `ColourSpec`: a colour by name (`ColourSpec.named(ColourName("ink!50"))`) or the numbers of a
`ColourModel` (`ColourSpec.of(0.1, 0.2, 0.3)` with `ColourModel.RGB_UNIT`, `ColourSpec.html("223344")` with
`ColourModel.HTML`). A call whose model and spec do not fit is `TM-C036`."""

import dataclasses
import enum
import math
import re
from typing import Any

from texmodel.components import Command
from texmodel.errors import ValueRuleError, Violation
from texmodel.interface import ColourName
from texmodel.package import Package
from texmodel.types import AsTeX, Choice, Name, Text, plain_number

package = Package("xcolor", prefix="", adopted=True)


@enum.unique
class ColourModel(Choice):
    """A colour model xcolor reads: the components of `\\color[model]{...}` and `\\definecolor`."""

    RGB_UNIT = "rgb"
    RGB_255 = "RGB"
    HTML = "HTML"
    CMY = "cmy"
    CMYK = "cmyk"
    HSB = "hsb"
    HSB_240 = "HSB"
    GRAY = "gray"
    GRAY_15 = "Gray"
    WAVE = "wave"


_COMPONENTS = {
    ColourModel.RGB_UNIT: 3,
    ColourModel.RGB_255: 3,
    ColourModel.CMY: 3,
    ColourModel.CMYK: 4,
    ColourModel.HSB: 3,
    ColourModel.HSB_240: 3,
    ColourModel.GRAY: 1,
    ColourModel.GRAY_15: 1,
    ColourModel.WAVE: 1,
}
_HTML = re.compile(r"[0-9A-Fa-f]{6}")


@enum.unique
class SpecKind(enum.Enum):
    """What a `ColourSpec` holds."""

    NAME = "name"
    NUMBERS = "numbers"
    HTML = "html"


@dataclasses.dataclass(frozen=True)
class ColourSpec(AsTeX):
    r"""The colour argument of `\color`, `\textcolor` and `\definecolor`. Build it with `named`, `of` or `html`."""

    kind: SpecKind
    text: str

    @classmethod
    def named(cls, name: "ColourName | type[Any] | str") -> "ColourSpec":
        """A colour by name or xcolor expression: `ColourSpec.named(ColourName("ink", tint=0.5))`, a registered colour
        value, or a name as a string (checked as a `ColourName`)."""
        return cls(SpecKind.NAME, ColourName(name))

    @classmethod
    def of(cls, *components: float) -> "ColourSpec":
        """The components of a model, comma separated: `ColourSpec.of(0.1, 0.2, 0.3)`. Finite and not negative."""
        if not components or not all(math.isfinite(c) and c >= 0 for c in components):
            raise ValueRuleError(
                "ColourSpec.of: give one or more finite components, not negative",
                code="TM-C042",
                hint="of(0.1, 0.2, 0.3)",
            )
        return cls(SpecKind.NUMBERS, ",".join(plain_number(c) for c in components))

    @classmethod
    def html(cls, digits: str) -> "ColourSpec":
        """Six hex digits: `ColourSpec.html("223344")`, for `ColourModel.HTML`."""
        if not _HTML.fullmatch(digits):
            raise ValueRuleError(
                f"ColourSpec.html({digits!r}): give six hex digits", code="TM-C043", hint='html("223344")'
            )
        return cls(SpecKind.HTML, digits.upper())

    def render(self) -> str:
        return self.text

    def fits(self, model: ColourModel | None) -> bool:
        """Whether `model` (none: a name) reads this spec."""
        if model is None:
            return self.kind is SpecKind.NAME
        if model is ColourModel.HTML:
            return self.kind is SpecKind.HTML
        return self.kind is SpecKind.NUMBERS and self.text.count(",") + 1 == _COMPONENTS[model]


def _fits(node: Any, path: str) -> list[Violation]:  # noqa: ANN401  # a check is given any node
    model = getattr(node, "model", None)  # `\colorlet` has none: its spec is a name
    if node.spec.fits(model):
        return []
    named = "a colour name" if model is None else f"the {model.value} components"
    return [
        Violation("TM-C036", f"{path}.spec", f"spec {node.spec.text!r} is not {named}", hint="match model and spec")
    ]


@package.command
class DefineColor(Command):
    r"""Name a colour: `\definecolor{ink}{HTML}{223344}`."""

    cs = "definecolor"
    checks = [_fits]
    name: Name
    model: ColourModel
    spec: ColourSpec


@package.command
class ColorLet(Command):
    r"""Name a colour by mixing others: `\colorlet{tmb}{tmink!50}`."""

    cs = "colorlet"
    checks = [_fits]
    name: Name
    spec: ColourSpec


@package.command
class Color(Command):
    r"""Switch the text colour: `\color{ink}` or `\color[rgb]{1,0,0}`."""

    cs = "color"
    checks = [_fits]
    spec: ColourSpec
    model: ColourModel | None = None


@package.command
class TextColor(Command):
    r"""Coloured text: `\textcolor{ink}{words}`."""

    cs = "textcolor"
    checks = [_fits]
    spec: ColourSpec
    text: Text
    model: ColourModel | None = None
