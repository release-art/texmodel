"""Field types (T1): the closed vocabulary a component field may use.

`Text` is plain `str` to a type checker, so `Fact("A soft woof.")` type-checks, and a marker at runtime, so the renderer
and (later) the escaper know the field holds untrusted text that must be escaped on render (T3).
"""

import dataclasses
import enum
import math
import re
from decimal import Decimal
from fractions import Fraction
from typing import TYPE_CHECKING, Annotated, ClassVar, Final

from .errors import DeclarationError, ValidationError

if TYPE_CHECKING:
    from pydantic_core import CoreSchema


class _TextMarker:
    def __repr__(self) -> str:
        return "Text"


TEXT: Final = _TextMarker()
Text = Annotated[str, TEXT]


class _ToggleMarker:
    def __repr__(self) -> str:
        return "Toggle"


TOGGLE: Final = _ToggleMarker()  # marks `texmodel.std.etoolbox.Toggle`, which a `Value` reads as an etoolbox toggle


class _PdfMarker:
    def __repr__(self) -> str:
        return "PdfString"


PDF: Final = _PdfMarker()
PdfString = Annotated[str, PDF]  # text for the inside of a PDF literal string, see `pdf_escape`

_ESCAPES = str.maketrans(
    {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
)


def escape(text: str) -> str:
    """`Text` on render (T3): every TeX special becomes its literal; one pass, so output is never re-escaped."""
    return text.translate(_ESCAPES)


_PDF_SAFE = re.compile(r"[\\(){}%#&$_^~\x00-\x1f\x7f]")


def pdf_escape(text: str) -> str:
    """`PdfString` on render (§21a 9): the body of a PDF literal string that cannot end early and that a reader decodes
    to `text`.

    A character that opens or ends a string (`\\ ( )`), that TeX reads as markup (`% # & $ _ ^ ~ { }`) or that is a
    control character becomes a three-digit octal escape (`\\050`); so does a space after a space, since TeX reads a
    run of spaces as one. Text with a non-ASCII character is written as UTF-16BE with a byte order mark, every byte an
    octal escape: a PDF text string is PDFDocEncoding or UTF-16BE, never UTF-8. A lone surrogate raises
    `UnicodeEncodeError`. The result is emitted inside `\\detokenize{}`."""
    if not text.isascii():
        return "".join(f"\\{b:03o}" for b in ("\ufeff" + text).encode("utf-16-be"))
    out = _PDF_SAFE.sub(lambda m: f"\\{ord(m[0]):03o}", text)
    return re.sub(r"(?<= ) ", r"\\040", out)


def balanced(tex: str) -> bool:
    """Braces balance, ignoring escaped ones and comments: unbalanced TeX would swallow what follows it."""
    depth = 0
    i = 0
    while i < len(tex):
        c = tex[i]
        if c == "\\":
            i += 1  # the escaped character is not a brace
        elif c == "%":
            while i < len(tex) and tex[i] != "\n":
                i += 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0


@dataclasses.dataclass(frozen=True)
class Raw:
    """TeX passed through unescaped, only where a field is declared `Raw` (T3). A distinct class, never a `str`."""

    tex: str

    def __post_init__(self) -> None:
        if not balanced(self.tex):
            raise ValidationError("Raw: unbalanced braces", code="TM-C007", hint="close every { and } in the TeX")

    @classmethod
    def __get_pydantic_core_schema__(cls, source: object, handler: object) -> CoreSchema:
        """Data gives `Raw` as a string (S, D2); a `Raw` passes as it is; unbalanced braces are a data error."""
        from pydantic_core import core_schema as cs

        def make(value: object) -> Raw:
            if isinstance(value, cls):
                return value
            if not isinstance(value, str):
                raise ValueError("expected TeX as a string")  # noqa: TRY004  # pydantic reports ValueError, not TypeError
            try:
                return cls(value)
            except ValidationError as exc:
                raise ValueError(str(exc)) from exc

        return cs.json_or_python_schema(
            json_schema=cs.chain_schema([cs.str_schema(), cs.no_info_plain_validator_function(make)]),
            python_schema=cs.no_info_plain_validator_function(make),
            serialization=cs.plain_serializer_function_ser_schema(lambda raw: raw.tex),
        )


class Choice(enum.Enum):
    """A closed set a field takes (T1): subclass it, decorate the subclass with `@enum.unique`, and give each member the
    TeX it stands for, a `Raw` (passes through) or a `str` (escaped as text). Data names a member by its name."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}.{self.name}"

    @classmethod
    def __get_pydantic_core_schema__(cls, source: object, handler: object) -> CoreSchema:
        from pydantic_core import core_schema as cs

        names = list(cls.__members__)

        def make(value: object) -> Choice:
            if isinstance(value, cls):
                return value
            if isinstance(value, str) and value in names:
                return cls[value]
            raise ValueError(f"expected one of {names}")

        return cs.json_or_python_schema(
            json_schema=cs.chain_schema([cs.literal_schema(names), cs.no_info_plain_validator_function(make)]),
            python_schema=cs.no_info_plain_validator_function(make),
            serialization=cs.plain_serializer_function_ser_schema(lambda member: member.name),
        )


# --- Values (T2, T4, T5): what a `Value[T]` holds. Immutable, validated on construction, stable to format. ---

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


def plain_number(x: float) -> str:
    """A number as TeX reads it: no exponent, no trailing zeros (`0.5`, `2`)."""
    return _plain(_decimal(x))


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

    @staticmethod
    def expr(tex: "Raw | str") -> "LengthExpr":
        """A TeX length expression, which has no size in Python: `Length.expr(r"\\linewidth")`,
        `Length.expr(r"0.5\\textwidth")`. Written as it is, braces balanced; a plain `str` is not a length, so this is
        how to say one."""
        return LengthExpr(tex)

    @classmethod
    def __get_pydantic_core_schema__(cls, source: object, handler: object) -> CoreSchema:
        """Data gives a length as `"2mm"`, or `{"expr": "\\linewidth"}` for an expression."""
        from pydantic_core import core_schema as cs

        def make(value: object) -> Length:
            try:
                if isinstance(value, Length):
                    return value
                if isinstance(value, str):
                    return Length(value)
                if isinstance(value, dict) and set(value) == {"expr"} and isinstance(value["expr"], str):  # pyright: ignore[reportUnknownArgumentType]
                    return LengthExpr(value["expr"])
            except (DeclarationError, ValidationError) as exc:
                raise ValueError(str(exc)) from exc
            raise ValueError('expected a length such as "2mm", or {"expr": "\\\\linewidth"}')

        return cs.json_or_python_schema(
            json_schema=cs.chain_schema(
                [cs.union_schema([cs.str_schema(), cs.dict_schema()]), cs.no_info_plain_validator_function(make)]
            ),
            python_schema=cs.no_info_plain_validator_function(make),
            serialization=cs.plain_serializer_function_ser_schema(
                lambda length: {"expr": length.tex} if isinstance(length, LengthExpr) else str(length)
            ),
        )


@dataclasses.dataclass(frozen=True, init=False)
class LengthExpr(Length):
    """A TeX length expression (`Length.expr`): a `Length` wherever one is asked for; only TeX knows its size."""

    tex: str

    def __init__(self, tex: "Raw | str") -> None:  # noqa: PLW0231  # a different constructor from Length's
        text = tex.tex if isinstance(tex, Raw) else Raw(tex).tex
        if not text.strip():
            raise DeclarationError("Length.expr: empty", code="TM-M016")
        object.__setattr__(self, "value", Decimal(0))
        object.__setattr__(self, "unit", "")
        object.__setattr__(self, "tex", text)

    def __str__(self) -> str:
        return self.tex

    @property
    def inches(self) -> Fraction:
        raise DeclarationError(f"{self}: a TeX expression has no size in Python", code="TM-M016")


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
