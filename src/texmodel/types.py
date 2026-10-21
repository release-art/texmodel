"""Field types (T1): the closed vocabulary a component field may use.

`Text` is plain `str` to a type checker, so `Fact("A soft woof.")` type-checks, and a marker at runtime, so the renderer
and (later) the escaper know the field holds untrusted text that must be escaped on render (T3).
"""

import dataclasses
import math
import re
from decimal import Decimal
from fractions import Fraction
from typing import Annotated, ClassVar, Final

from .errors import DeclarationError


class _TextMarker:
    def __repr__(self) -> str:
        return "Text"


TEXT: Final = _TextMarker()
Text = Annotated[str, TEXT]


# --- Values (T2, T4, T5): what a `Value[T]` holds. Immutable, validated on construction, stable to format. ---

Bool = bool
"""A TeX `\\newif`; plain `bool`."""

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_LENGTH = re.compile(rf"(?P<n>{_NUMBER})(?P<u>[a-z]+)")
_INCHES_PER = {  # None: relative to the font, no fixed size
    "in": Fraction(1),
    "mm": Fraction(10, 254),
    "cm": Fraction(100, 254),
    "pt": Fraction(100, 7227),  # TeX points: 72.27 to the inch
    "bp": Fraction(1, 72),  # big (PostScript) points: 72 to the inch
    "pc": Fraction(1200, 7227),
    "em": None,
    "ex": None,
}


def _plain(d: Decimal) -> str:
    """No exponent, no trailing zeros, no `-0`: `2.0` -> `2`, `1e-05` -> `0.00001`."""
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _decimal(x: float) -> Decimal:
    return Decimal(repr(float(x)))


@dataclasses.dataclass(frozen=True, init=False)
class Length:
    """A TeX dimension: `Length("2mm")`, `Length(1.5, "pt")`. Units are kept as written, never converted."""

    value: Decimal
    unit: str

    def __init__(self, value: str | float, unit: str | None = None) -> None:
        hint = 'write a number and a unit (mm cm in pt bp pc em ex), e.g. Length("2mm")'
        if unit is None:
            m = _LENGTH.fullmatch(value) if isinstance(value, str) else None
            if not m:
                raise DeclarationError(f"Length({value!r}): not a number with a unit", code="TM-M016", hint=hint)
            value, unit = m["n"], m["u"]
        if unit not in _INCHES_PER:
            raise DeclarationError(f"Length: unknown unit {unit!r}", code="TM-M016", hint=hint)
        if isinstance(value, str):
            if not re.fullmatch(_NUMBER, value):
                raise DeclarationError(f"Length({value!r}): not a number", code="TM-M016", hint=hint)
            number = Decimal(value)
        elif math.isfinite(value):
            number = _decimal(value)
        else:
            raise DeclarationError(f"Length({value!r}): not finite", code="TM-M016", hint=hint)
        object.__setattr__(self, "value", number)
        object.__setattr__(self, "unit", unit)

    def __str__(self) -> str:
        return f"{_plain(self.value)}{self.unit}"

    @property
    def inches(self) -> Fraction:
        """Exact size in inches (T4); `em` and `ex` depend on the font and have none."""
        per = _INCHES_PER[self.unit]
        if per is None:
            raise DeclarationError(f"{self}: {self.unit} is relative to the font", code="TM-M016")
        return Fraction(self.value) * per


class _Colour:
    """Components in [0, 1], refused outside it; `str()` is what `\\definecolor` takes."""

    model: ClassVar[str]

    def __post_init__(self) -> None:
        for name, v in vars(self).items():
            if not 0 <= v <= 1:  # also false for nan
                raise DeclarationError(
                    f"{type(self).__name__}.{name}={v!r}: components are in [0, 1]", code="TM-M017", path=name
                )

    def __str__(self) -> str:
        return ",".join(_plain(_decimal(v)) for v in vars(self).values())


@dataclasses.dataclass(frozen=True)
class CMYK(_Colour):
    c: float
    m: float
    y: float
    k: float
    model: ClassVar[str] = "cmyk"


@dataclasses.dataclass(frozen=True)
class RGB(_Colour):
    r: float
    g: float
    b: float
    model: ClassVar[str] = "rgb"


@dataclasses.dataclass(frozen=True)
class Gray(_Colour):
    g: float
    model: ClassVar[str] = "gray"


Colour = CMYK | RGB | Gray
"""One colour model each; there is no conversion between them (T5)."""
