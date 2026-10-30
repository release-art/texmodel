"""Cell formats."""

import dataclasses
import datetime
import decimal
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, ClassVar, Final

from ...errors import DeclarationError
from ...std import tabularray as t
from ...std.graphicx import IncludeGraphics, IncludeGraphicsOptions
from ...types import Length, Raw, escape

NUMBERS: Final = (int, float, Decimal)
_SPACE: Final = r"\,"  # a thin space: the group separator of digits


# --- formats -------------------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Format:
    """How a value of a column is written: a pure function from value to escaped TeX. `missing` stands for `None`."""

    missing: str = dataclasses.field(default="–", kw_only=True)
    align: ClassVar[t.HAlign] = t.HAlign.LEFT
    valign: ClassVar[t.VAlign | None] = None
    numeric: ClassVar[bool] = False

    def tex(self, value: object) -> str:
        return self.missing if value is None else self._tex(value)

    def _tex(self, value: object) -> str:
        raise NotImplementedError


@dataclasses.dataclass(frozen=True)
class Text(Format):
    """Text, escaped; a `Raw` passes as written. Line breaks and runs of spaces become one space."""

    def _tex(self, value: object) -> str:
        return value.tex if isinstance(value, Raw) else escape(" ".join(str(value).split()))


@dataclasses.dataclass(frozen=True)
class Number(Format):
    r"""A number at `decimals` places (rounded half up), digits grouped in threes from four digits (`thousands`), with
    `point` and `separator` as TeX (`Number(2, point="{,}")` is a decimal comma), a true minus, a plus with `sign`."""

    decimals: int = 0
    thousands: bool = True
    point: str = "."
    separator: str = _SPACE
    sign: bool = False
    minus: str = "−"
    align: ClassVar[t.HAlign] = t.HAlign.RIGHT
    numeric: ClassVar[bool] = True

    def __post_init__(self) -> None:
        if self.decimals < 0:
            raise DeclarationError(f"{type(self).__name__}: decimals {self.decimals} is not 0 or more", code="TM-M077")

    def _scaled(self, value: Decimal) -> Decimal:
        return value

    def _prefix(self) -> str:
        return ""

    def _suffix(self) -> str:
        return ""

    def _tex(self, value: object) -> str:
        if isinstance(value, bool) or not isinstance(value, NUMBERS):
            raise TypeError(f"{type(self).__name__}: {value!r} is not a number")
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError(f"{type(self).__name__}: {value!r} is not finite")
        number = self._scaled(number).quantize(Decimal(1).scaleb(-self.decimals), rounding=decimal.ROUND_HALF_UP)
        whole, _, fraction = f"{abs(number):f}".partition(".")
        if self.thousands and len(whole) > 3:
            groups = [whole[max(i - 3, 0) : i] for i in range(len(whole), 0, -3)]
            whole = self.separator.join(reversed(groups))
        text = self._prefix() + whole + (self.point + fraction if fraction else "") + self._suffix()
        return (self.minus if number < 0 else "+" if self.sign and number > 0 else "") + text


@dataclasses.dataclass(frozen=True)
class Percent(Number):
    r"""A fraction as a percentage: `0.123` is `12.3 %` with `Percent(1)`."""

    def _scaled(self, value: Decimal) -> Decimal:
        return value * 100

    def _suffix(self) -> str:
        return r"\,\%"


@dataclasses.dataclass(frozen=True)
class Money(Number):
    r"""An amount with a currency `symbol` (TeX: `"€"`, `r"\$"`) before it, or after it with `after=True`."""

    decimals: int = 2
    symbol: str = dataclasses.field(default="", kw_only=True)
    after: bool = dataclasses.field(default=False, kw_only=True)

    def _prefix(self) -> str:
        return "" if self.after else self.symbol

    def _suffix(self) -> str:
        return f"{_SPACE}{self.symbol}" if self.after and self.symbol else ""


@dataclasses.dataclass(frozen=True)
class Date(Format):
    """A date or datetime by a `strftime` pattern (the portable directives; month and day names are English)."""

    pattern: str = "%Y-%m-%d"

    def _tex(self, value: object) -> str:
        if not isinstance(value, datetime.date):
            raise TypeError(f"Date: {value!r} is not a date")
        return escape(value.strftime(self.pattern))


@dataclasses.dataclass(frozen=True)
class Label(Format):
    """The text for each value, for an enum, a boolean or a code: `Label({True: "Yes", False: "No"})`. A value with no
    text is an error; a `Raw` text passes as written."""

    texts: Mapping[Any, str | Raw]

    def _tex(self, value: object) -> str:
        if value not in self.texts:
            raise ValueError(f"Label: no text for {value!r}")
        text = self.texts[value]
        return text.tex if isinstance(text, Raw) else escape(text)


@dataclasses.dataclass(frozen=True)
class Block(Format):
    r"""A cell of its own typesetting, in a group: a minipage, a list, a nested table (`Raw(inner.render())`) or a
    paragraph in a column with a `width`. A `Raw` passes as written, text is escaped; the group keeps an `&` or `\\`
    inside it from ending the cell. Aligned at the head (first baseline) of the row, which holds with images."""

    valign: ClassVar[t.VAlign | None] = t.VAlign.HEAD

    def _tex(self, value: object) -> str:
        return "{" + (value.tex if isinstance(value, Raw) else escape(str(value))) + "}"


@dataclasses.dataclass(frozen=True)
class Image(Block):
    """A picture by its path, `width` wide. The document's package needs `graphicx` (`std.graphicx`)."""

    width: Length | None = None

    def _tex(self, value: object) -> str:
        path = str(value)
        if set(path) & set("{}\\%#"):
            raise ValueError(f"Image: {path!r} has a character a path cannot")
        options = IncludeGraphicsOptions(width=self.width) if self.width else None
        return "{" + IncludeGraphics(path=Raw(path), options=options).render() + "}"
