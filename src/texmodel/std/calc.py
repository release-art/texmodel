r"""calc: infix arithmetic in the arguments of `\setcounter`, `\addtocounter`, `\setlength`, `\addtolength`.

The package adds no new kind of command: it lets these four (and the many commands that read a length through
`\setlength`) take an expression, and adds `\settototalheight`. The expression language is typed, and so is this header:

- **Types.** An `IntExpr` is a TeX number (`\setcounter`), a `DimenExpr` a rigid length, a `GlueExpr` a length with
  stretch and shrink. Both lengths are `Length`s, so they fit the commands that read a length through `\setlength`
  (`\makebox`, `\raisebox`, `\parbox`, `\hspace`, `\vspace`, `\rule`, a `minipage` or `p{}` width). Not those that
  hand it to a primitive (`\fontsize`, `\hskip`): their fields stay `Raw`.
- **Terms.** `integer(3)`, `counter_value("c")`, `count_register(Raw(r"\thepage"))`, `dimen(Length("2mm"))`,
  `dimen(Raw(r"\textwidth"))`, `glue(Length("3pt"), stretch=Length("1pt"))`, and the text sizes `widthof("text")`,
  `heightof`, `depthof`, `totalheightof`.
- **Operators.** `+ - * /` and unary `-`, with Python's precedence; parentheses are written where the result needs them.
  Lengths add to lengths; a length is multiplied or divided by an integer (`3`, `counter_value("c")`, a parenthesised
  integer expression), by `real("1.5")` or by `ratio(a, b)`. `2cm + 4` is a `TypeError`, as it is a TeX error.
- **Functions.** `maxof(a, b)` and `minof(a, b)` of two expressions of one type.

```python
from texmodel.std.calc import SetLength, dimen, maxof, ratio, real, widthof

SetLength(Raw(r"\parindent"), maxof(dimen(Length("3pt")), widthof("Notes") * real(0.5)))
# \setlength{\parindent}{\maxof{3pt}{\widthof{Notes}*\real{0.5}}}
```

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

import dataclasses
import re
from typing import overload

from texmodel.components import Command
from texmodel.errors import DeclarationError
from texmodel.package import Package
from texmodel.types import Length, LengthExpr, Raw, escape, plain_number

package = Package("calc", prefix="", adopted=True)

SUM, TERM, ATOM = 1, 2, 3  # how tightly an expression binds: `a+b`, `a*b`, a single quantity

_DECIMAL = re.compile(r"\s*(?:[+-]\s*)*(?:\d+(?:[.,]\d*)?|[.,]\d+)\s*")


def _group(e: "IntExpr | DimenExpr | GlueExpr", need: int) -> str:
    """The text of `e` as an operand that binds at least `need`: in parentheses if it binds less."""
    return e.tex if e.prec >= need else f"({e.tex})"


def _right(e: "IntExpr | DimenExpr | GlueExpr", op: int) -> str:
    """The right operand of an operator at level `op`: parenthesised if it binds no tighter, or starts with a sign."""
    return f"({e.tex})" if e.prec <= op or e.tex[:1] in "+-" else e.tex


@dataclasses.dataclass(frozen=True)
class Real:
    r"""A real number to multiply or divide by: `real(1.5)` is `\real{1.5}`."""

    tex: str


@dataclasses.dataclass(frozen=True)
class Ratio:
    r"""The quotient of two lengths to multiply or divide by: `ratio(a, b)` is `\ratio{a}{b}`."""

    tex: str


def real(value: float | str) -> Real:
    r"""`\real{1.5}`. A `str` is a decimal constant with optional signs (`"-1.5"`, `"1,5"`); a float is plain."""
    text = plain_number(value) if isinstance(value, int | float) and not isinstance(value, bool) else value
    if not isinstance(text, str) or not _DECIMAL.fullmatch(text):
        raise DeclarationError(f"real({value!r}): not a decimal constant", code="TM-M016")
    return Real(rf"\real{{{text}}}")


def ratio(numerator: "DimenExpr | Length", denominator: "DimenExpr | Length") -> Ratio:
    r"""`\ratio{n}{d}`: the number `n / d`, for two lengths."""
    return Ratio(rf"\ratio{{{dimen(numerator).tex}}}{{{dimen(denominator).tex}}}")


type Multiplier = int | IntExpr | Real | Ratio


def _factor(m: Multiplier) -> str:
    """What follows `*` or `/`: an integer, a counter or parenthesised integer expression, `\\real` or `\\ratio`."""
    if isinstance(m, Real | Ratio):
        return m.tex
    if isinstance(m, int) and not isinstance(m, bool):
        return f"({m})" if m < 0 else str(m)
    if isinstance(m, IntExpr):
        return _group(m, ATOM)
    raise TypeError(f"expected an integer, an IntExpr, real() or ratio(), not {type(m).__name__}")


@dataclasses.dataclass(frozen=True)
class IntExpr(Raw):
    """An integer expression: what `\\setcounter` takes. Built by `integer`, `counter_value`, `maxof`, `minof` and
    arithmetic on those."""

    prec: int = dataclasses.field(default=ATOM, compare=False, repr=False)

    def __str__(self) -> str:
        return self.tex

    def _op(self, op: str, level: int, other: "int | IntExpr | Real | Ratio") -> "IntExpr":
        return IntExpr(f"{_group(self, level)}{op}{_factor(other)}", level)

    def _sum(self, op: str, other: "int | IntExpr") -> "IntExpr":
        right = integer(other) if isinstance(other, int) and not isinstance(other, bool) else other
        if not isinstance(right, IntExpr):
            raise TypeError(f"cannot {'add' if op == '+' else 'subtract'} {type(other).__name__} and an IntExpr")
        return IntExpr(f"{_group(self, SUM)}{op}{_right(right, SUM)}", SUM)

    def __add__(self, other: "int | IntExpr") -> "IntExpr":
        return self._sum("+", other)

    def __radd__(self, other: int) -> "IntExpr":
        return integer(other)._sum("+", self)  # noqa: SLF001

    def __sub__(self, other: "int | IntExpr") -> "IntExpr":
        return self._sum("-", other)

    def __rsub__(self, other: int) -> "IntExpr":
        return integer(other)._sum("-", self)  # noqa: SLF001

    def __mul__(self, other: Multiplier) -> "IntExpr":
        return self._op("*", TERM, other)

    def __rmul__(self, other: int) -> "IntExpr":
        return integer(other)._op("*", TERM, self)  # noqa: SLF001

    def __truediv__(self, other: Multiplier) -> "IntExpr":
        return self._op("/", TERM, other)

    def __neg__(self) -> "IntExpr":
        return self._op("*", TERM, real(-1))

    def __pos__(self) -> "IntExpr":
        return self


@dataclasses.dataclass(frozen=True, init=False)
class DimenExpr(LengthExpr):
    """A rigid length expression, a `Length` to a type checker. Built by `dimen`, the text sizes, `maxof`, `minof` and
    arithmetic on those."""

    prec: int = dataclasses.field(default=ATOM, compare=False, repr=False)

    def __init__(self, tex: Raw | str, prec: int = ATOM) -> None:  # noqa: PLW0231
        super().__init__(tex)
        object.__setattr__(self, "prec", prec)

    def _sum(self, op: str, other: "DimenExpr | Length") -> "DimenExpr | GlueExpr":
        if isinstance(other, GlueExpr):  # a dimen and a glue make a glue
            return GlueExpr(f"{_group(self, SUM)}{op}{_right(other, SUM)}", SUM)
        return DimenExpr(f"{_group(self, SUM)}{op}{_right(dimen(other), SUM)}", SUM)

    @overload
    def __add__(self, other: "GlueExpr") -> "GlueExpr": ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __add__(self, other: "DimenExpr | Length") -> "DimenExpr": ...
    def __add__(self, other: "DimenExpr | Length") -> "DimenExpr | GlueExpr":
        return self._sum("+", other)

    def __radd__(self, other: Length) -> "DimenExpr":
        return dimen(other)._sum("+", self)  # pyright: ignore[reportReturnType]  # noqa: SLF001

    @overload
    def __sub__(self, other: "GlueExpr") -> "GlueExpr": ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __sub__(self, other: "DimenExpr | Length") -> "DimenExpr": ...
    def __sub__(self, other: "DimenExpr | Length") -> "DimenExpr | GlueExpr":
        return self._sum("-", other)

    def __rsub__(self, other: Length) -> "DimenExpr":
        return dimen(other)._sum("-", self)  # pyright: ignore[reportReturnType]  # noqa: SLF001

    def __mul__(self, other: Multiplier) -> "DimenExpr":
        return DimenExpr(f"{_group(self, TERM)}*{_factor(other)}", TERM)

    def __rmul__(self, other: Multiplier) -> "DimenExpr":
        return self * other  # the value is the same; calc wants the length first

    def __truediv__(self, other: Multiplier) -> "DimenExpr":
        return DimenExpr(f"{_group(self, TERM)}/{_factor(other)}", TERM)

    def __neg__(self) -> "DimenExpr":
        return self * real(-1)

    def __pos__(self) -> "DimenExpr":
        return self


@dataclasses.dataclass(frozen=True, init=False)
class GlueExpr(LengthExpr):
    """A length expression with stretch and shrink, a `Length` to a type checker. Built by `glue`; a `DimenExpr` or
    `Length` added to it is glue too. Multiplying or dividing by a real number drops the stretch and shrink (TeX)."""

    prec: int = dataclasses.field(default=ATOM, compare=False, repr=False)

    def __init__(self, tex: Raw | str, prec: int = ATOM) -> None:  # noqa: PLW0231
        super().__init__(tex)
        object.__setattr__(self, "prec", prec)

    def _sum(self, op: str, other: "GlueExpr | DimenExpr | Length") -> "GlueExpr":
        right = other if isinstance(other, GlueExpr | DimenExpr) else dimen(other)
        return GlueExpr(f"{_group(self, SUM)}{op}{_right(right, SUM)}", SUM)

    def __add__(self, other: "GlueExpr | DimenExpr | Length") -> "GlueExpr":
        return self._sum("+", other)

    def __radd__(self, other: "DimenExpr | Length") -> "GlueExpr":
        return GlueExpr(f"{_group(dimen(other), SUM)}+{_right(self, SUM)}", SUM)

    def __sub__(self, other: "GlueExpr | DimenExpr | Length") -> "GlueExpr":
        return self._sum("-", other)

    def __rsub__(self, other: "DimenExpr | Length") -> "GlueExpr":
        return GlueExpr(f"{_group(dimen(other), SUM)}-{_right(self, SUM)}", SUM)

    def __mul__(self, other: Multiplier) -> "GlueExpr":
        return GlueExpr(f"{_group(self, TERM)}*{_factor(other)}", TERM)

    def __rmul__(self, other: Multiplier) -> "GlueExpr":
        return self * other

    def __truediv__(self, other: Multiplier) -> "GlueExpr":
        return GlueExpr(f"{_group(self, TERM)}/{_factor(other)}", TERM)

    def __neg__(self) -> "GlueExpr":
        return self * real(-1)

    def __pos__(self) -> "GlueExpr":
        return self


def integer(value: int) -> IntExpr:
    """A literal number."""
    if not isinstance(value, int) or isinstance(value, bool):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(f"integer() takes an int, not {type(value).__name__}")
    return IntExpr(str(value))


def counter_value(counter: Raw | str) -> IntExpr:
    r"""The value of a counter: `\value{c}`. A `str` is the counter's name."""
    return IntExpr(rf"\value{{{counter.tex if isinstance(counter, Raw) else counter}}}")


def count_register(register: Raw) -> IntExpr:
    r"""A TeX number that is not `\value{counter}`: a count register (`Raw(r"\count255")`) or a macro that expands to
    digits (`Raw(r"\thepage")`)."""
    return IntExpr(register.tex)


def dimen(value: "Length | DimenExpr | Raw") -> DimenExpr:
    r"""A length as an expression: a `Length`, or a `Raw` register or macro (`Raw(r"\textwidth")`). One that is
    already an expression is returned as it is."""
    if isinstance(value, DimenExpr):
        return value
    if isinstance(value, Raw):
        return DimenExpr(value)
    if isinstance(value, GlueExpr):
        raise TypeError("a glue expression is not a dimen")
    return DimenExpr(str(value))


def glue(
    natural: "Length | Raw", stretch: "Length | Raw | None" = None, shrink: "Length | Raw | None" = None
) -> GlueExpr:
    r"""A length with stretch and shrink: `3pt plus 1pt minus 1pt`. A `Raw` stretch is for infinity (`Raw("1fill")`)."""

    def text(x: "Length | Raw") -> str:
        return x.tex if isinstance(x, Raw) else str(x)

    parts = [text(natural)]
    if stretch is not None:
        parts.append(f"plus {text(stretch)}")
    if shrink is not None:
        parts.append(f"minus {text(shrink)}")
    return GlueExpr(" ".join(parts), SUM if len(parts) > 1 else ATOM)


def _text(text: "Raw | str") -> str:
    return text.tex if isinstance(text, Raw) else escape(text)


def widthof(text: "Raw | str") -> DimenExpr:
    r"""The natural width of some text set in LR mode: `\widthof{text}` (a `str` is escaped)."""
    return DimenExpr(rf"\widthof{{{_text(text)}}}")


def heightof(text: "Raw | str") -> DimenExpr:
    r"""Its height above the baseline: `\heightof{text}`."""
    return DimenExpr(rf"\heightof{{{_text(text)}}}")


def depthof(text: "Raw | str") -> DimenExpr:
    r"""Its depth below the baseline: `\depthof{text}`."""
    return DimenExpr(rf"\depthof{{{_text(text)}}}")


def totalheightof(text: "Raw | str") -> DimenExpr:
    r"""Its height plus depth: `\totalheightof{text}`."""
    return DimenExpr(rf"\totalheightof{{{_text(text)}}}")


@overload
def maxof(a: IntExpr, b: IntExpr) -> IntExpr: ...
@overload
def maxof(a: GlueExpr, b: "GlueExpr | DimenExpr | Length") -> GlueExpr: ...  # pyright: ignore[reportOverlappingOverload]
@overload
def maxof(a: "DimenExpr | Length", b: "GlueExpr") -> GlueExpr: ...
@overload
def maxof(a: "DimenExpr | Length", b: "DimenExpr | Length") -> DimenExpr: ...
def maxof(a: object, b: object) -> "IntExpr | DimenExpr | GlueExpr":
    r"""The larger of two expressions of one type: `\maxof{a}{b}`."""
    return _extreme(r"\maxof", a, b)


@overload
def minof(a: IntExpr, b: IntExpr) -> IntExpr: ...
@overload
def minof(a: GlueExpr, b: "GlueExpr | DimenExpr | Length") -> GlueExpr: ...  # pyright: ignore[reportOverlappingOverload]
@overload
def minof(a: "DimenExpr | Length", b: "GlueExpr") -> GlueExpr: ...
@overload
def minof(a: "DimenExpr | Length", b: "DimenExpr | Length") -> DimenExpr: ...
def minof(a: object, b: object) -> "IntExpr | DimenExpr | GlueExpr":
    r"""The smaller of two expressions of one type: `\minof{a}{b}`."""
    return _extreme(r"\minof", a, b)


def _extreme(name: str, a: object, b: object) -> "IntExpr | DimenExpr | GlueExpr":
    if isinstance(a, IntExpr) and isinstance(b, IntExpr):
        return IntExpr(rf"{name}{{{a.tex}}}{{{b.tex}}}")
    if isinstance(a, IntExpr) or isinstance(b, IntExpr):
        raise TypeError(f"{name[1:]}() takes two expressions of one type, not an IntExpr and a length")
    if not isinstance(a, Length) or not isinstance(b, Length):
        raise TypeError(f"{name[1:]}() takes two IntExprs or two lengths")
    both_dimen = not isinstance(a, GlueExpr) and not isinstance(b, GlueExpr)
    first, second = (dimen(a), dimen(b)) if both_dimen else (a, b)
    text = rf"{name}{{{first}}}{{{second}}}"
    return DimenExpr(text) if both_dimen else GlueExpr(text)


@package.command
class SetCounter(Command):
    r"""Set a counter to an integer expression: `\setcounter{c}{3*\real{1.6}}`."""

    cs = "setcounter"
    counter: Raw
    value: IntExpr


@package.command
class AddToCounter(Command):
    r"""Add an integer expression to a counter."""

    cs = "addtocounter"
    counter: Raw
    value: IntExpr


@package.command
class SetLength(Command):
    r"""Set a length to a glue expression: `\setlength{\parskip}{\widthof{abc}*\real{0.68}}`."""

    cs = "setlength"
    length: Raw
    value: Length


@package.command
class AddToLength(Command):
    r"""Add a glue expression to a length."""

    cs = "addtolength"
    length: Raw
    value: Length


@package.command
class SetToTotalHeight(Command):
    r"""Set a length to the height plus depth of some text: `\settototalheight{\len}{Ag}`."""

    cs = "settototalheight"
    length: Raw
    text: Raw
