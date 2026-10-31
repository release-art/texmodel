r"""Macro interfaces: where each argument of a macro sits, how it is delimited, what it holds.

A component's fields are its arguments. A field's type says what it holds (`Text`, `Raw`, `Length`, `Colour`, `int`,
`bool`, a `Choice`, a tuple, a list, a `KeyVals`); `arg(...)` on the field says how it is written:

```python
class MakeBox(Command):                       # \makebox[3cm][c]{x}
    cs = "makebox"
    width: Length | None = arg(SQUARE, default=None, fill="")   # unset while `pos` is set: written as `[]`
    pos: Align | None = arg(SQUARE, default=None)
    content: Text

class Section(Command):                       # \section*[short]{long}
    cs = "section"
    starred: Star = arg(default=False)
    short: Text | None = arg(SQUARE, default=None)
    title: Text
```

An optional field without `arg()` is TeX's one optional argument, first, as `\newcommand` has it. A field with `arg()`,
a required one and a `Star` keep their declaration order. A signature `\newcommand` cannot express (several optional
arguments, other delimiters, tokens) is defined with `\NewDocumentCommand`.
"""

import dataclasses
import enum
import re
from collections.abc import Mapping
from typing import Annotated, Any, Final, Literal

from pydantic_core import core_schema

from ._internal.fields import FieldNotes, field_info
from .errors import DeclarationError
from .types import PROCESS, Choice, Plate, plain_number, plates_of


@dataclasses.dataclass(frozen=True)
class Delimiter:
    """The two characters around an argument: `[` `]` for an optional one, `{` `}` for a required one, or a pair of
    your own. One character each, different, neither a letter, digit, space or one of `\\ % #`."""

    open: str
    close: str

    def __post_init__(self) -> None:
        for ch in (self.open, self.close):
            if len(ch) != 1 or ch.isalnum() or ch.isspace() or ch in "\\%#":
                raise DeclarationError(
                    f"Delimiter({self.open!r}, {self.close!r}): each side is one character, "
                    "not a letter, digit, space or \\ % #",
                    code="TM-M036",
                )
        if self.open == self.close:
            raise DeclarationError(f"Delimiter({self.open!r}, {self.close!r}): the sides must differ", code="TM-M036")


BRACE: Final = Delimiter("{", "}")
SQUARE: Final = Delimiter("[", "]")
PAREN: Final = Delimiter("(", ")")
ANGLE: Final = Delimiter("<", ">")


class _Marker:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return self.name


FLAG: Final = _Marker("Flag")
SWITCH: Final = _Marker("Switch")
ITEM: Final = _Marker("Item")

Flag = Annotated[bool, FLAG]
"""A key of a `KeyVals` written bare when set: `center`."""
Switch = Annotated[bool, SWITCH]
"""A key of a `KeyVals` written with its boolean literal when set: `clip=true`. Declared `Switch | None = None`; `None`
leaves it out."""
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9.+-]*")
_MACRO = re.compile(r"\\[A-Za-z@]+")
_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")


def colour_of(value: type[Any]) -> str:
    """The xcolor name of a colour value: its `colour_name`, else `<prefix>-<kebab>`: `colour_of(Ink)` is `ap-ink`."""
    kind = getattr(value, "__tm_kind__", None)
    if kind is None or not kind.named or not hasattr(value, "__tm_prefix__"):
        raise DeclarationError(
            f"colour_of({value.__name__}): not a registered colour value",
            code="TM-M066",
            path=value.__name__,
            hint="a Value[Colour], Value[Dual] or Value[SpotColour] registered with a package",
        )
    from ._internal.render import colour_name  # imports this module

    return str(value.colour_name or colour_name(value.__tm_prefix__, value.__name__))


XCOLOR: Final[Mapping[str, frozenset[str] | None]] = {
    "white": None,  # inks nothing, so any colour may be mixed with it
    "black": frozenset({Plate.K}),
    "darkgray": frozenset({Plate.K}),
    "gray": frozenset({Plate.K}),
    "lightgray": frozenset({Plate.K}),
    **dict.fromkeys(
        "blue brown cyan green lime magenta olive orange pink purple red teal violet yellow".split(), PROCESS
    ),
}
"""xcolor's base colours and the plates each inks in the `cmyk` model (`None`: none, `white`)."""


def constraint_of(value: type[Any]) -> frozenset[str]:
    """The plates a colour value may ink: its `plates`, else a spot's own plate, else the four process plates."""
    if value.plates is not None:
        return frozenset(value.plates)
    default = value.declared_default()
    inked: frozenset[str] = plates_of(default) if default is not None else frozenset[str]()
    return inked if inked - PROCESS else PROCESS


def _colour_ref(base: "str | type[Any]") -> str:
    return base if isinstance(base, str) else colour_of(base)


def _constraint(base: "str | type[Any]") -> frozenset[str] | None:
    """What a mix compares: a colour value's plates, xcolor's for its own names; `None` for `white` and for a name
    nothing here knows (a node checks that one against its package)."""
    return XCOLOR.get(base) if isinstance(base, str) else constraint_of(base)


class ColourName(str):
    """The name of a colour or an xcolor expression: `ColourName("red")`, `ColourName(Ink, tint=0.7)` (a colour value,
    tinted: `ap-ink!70`), `ColourName(Ink, tint=0.7, mix=Paper)` (`ap-ink!70!ap-paper`: 70% ink, 30% paper). A `str`, so
    a plain string is as good in a field; `names` are the colours it uses, which a node checks against its package
    (`TM-C022`). `tint` is a fraction, 0 to 1. Both ends of a mix may ink the same plates and no others (`TM-M068`,
    and `TM-C024` for any expression), so K-only ink is not mixed with a CMYK colour, a duotone or a spot."""

    __slots__ = ()

    def __new__(
        cls, base: "str | type[Any]", *, tint: float | None = None, mix: "str | type[Any] | None" = None
    ) -> "ColourName":
        text = _colour_ref(base)
        if tint is not None:
            if not 0 <= tint <= 1:
                raise DeclarationError(f"ColourName: tint {tint!r} is in [0, 1]", code="TM-M017", path="tint")
            text += f"!{plain_number(tint * 100)}"
            if mix is not None:
                text += f"!{_colour_ref(mix)}"
                ends = (_constraint(base), _constraint(mix))
                if None not in ends and ends[0] != ends[1]:
                    raise DeclarationError(
                        f"ColourName: {_colour_ref(base)} inks {sorted(ends[0] or ())} and {_colour_ref(mix)} "
                        f"inks {sorted(ends[1] or ())}",
                        code="TM-M068",
                        path="mix",
                        hint="both ends of a mix may ink the same plates and no others",
                    )
        elif mix is not None:
            raise DeclarationError("ColourName: mix= needs a tint=", code="TM-M067", path="mix")
        parts = text.split("!")
        if not all(_NAME.fullmatch(n) or _MACRO.fullmatch(n) for n in parts[0::2]) or not all(
            _NUMBER.fullmatch(n) and float(n) <= 100 for n in parts[1::2]
        ):
            raise DeclarationError(f"ColourName({text!r}): not `name`, `name!50` or `name!50!name`", code="TM-M067")
        return super().__new__(cls, text)

    @classmethod
    def macro(cls, base: "str | type[Any]") -> "ColourName":
        r"""A colour a macro names, read when the document is typeset: `ColourName.macro(r"\bbRowLabelColour")` or a
        registered value that defines the macro (`ColourName.macro(RowLabelColour)`). The package cannot check it, so it
        is left out of `names`. Like a name, it takes a tint: `ColourName(ColourName.macro(M), tint=0.5)`."""
        if isinstance(base, str):
            text = base if base.startswith("\\") else f"\\{base}"
        else:
            from .components import control_name  # imports this module

            if not hasattr(base, "__tm_cs__"):
                raise DeclarationError(
                    f"ColourName.macro({base.__name__}): not a registered value", code="TM-M067", path=base.__name__
                )
            text = f"\\{control_name(base)}"
        if not _MACRO.fullmatch(text):
            raise DeclarationError(f"ColourName.macro({base!r}): not a control word", code="TM-M067", path="macro")
        return cls(text)

    @property
    def names(self) -> tuple[str, ...]:
        """The colours the expression uses, in order; a macro is read at typesetting time, so it is not one."""
        return tuple(n for n in self.split("!")[0::2] if not _MACRO.fullmatch(n))

    @classmethod
    def __get_pydantic_core_schema__(cls, source: object, handler: Any) -> core_schema.CoreSchema:  # noqa: ANN401
        def make(value: str) -> "ColourName":
            try:
                return cls(value)
            except DeclarationError as exc:
                raise ValueError(str(exc)) from exc

        return core_schema.no_info_after_validator_function(
            make, core_schema.str_schema(), serialization=core_schema.plain_serializer_function_ser_schema(str)
        )


type Item[T] = Annotated[T, ITEM]
"""A value of a `KeyVals` written without a key: `thick`, `->`, `(1,2)`."""
type OptionalValue[T] = T | Literal[True]
"""A key of a `KeyVals` that takes a value or not: `True` writes the bare key, a `T` writes `key=value`."""


@dataclasses.dataclass(frozen=True)
class Token:
    """A single optional token after the command name: `Star` is `Token("*")`. The field is a `bool`, `= False`."""

    char: str

    def __post_init__(self) -> None:
        if len(self.char) != 1 or self.char.isalnum() or self.char.isspace() or self.char in "\\%#{}":
            raise DeclarationError(
                f"Token({self.char!r}): one character that is not a letter, digit or space", code="TM-M036"
            )


Star = Annotated[bool, Token("*")]
"""`\\section*`: the field is `True` when the star is written."""


@dataclasses.dataclass(frozen=True)
class SlotGroup:
    """Slots that are written together or not at all: give each member `arg(group=...)` with the same group."""

    name: str


@enum.unique
class Gap(enum.Enum):
    """What to write for an optional slot left unset while a later optional slot is set (`arg(fill=)`)."""

    UNDECLARED = "undeclared"  # not said: the declaration is refused when a later optional slot exists
    REFUSE = "refuse"  # the combination is a violation


@dataclasses.dataclass(frozen=True)
class ArgOptions:
    delimiter: Delimiter | None
    fill: str | Gap
    sep: str | None
    group: SlotGroup | None
    booleans: tuple[str, str] | None


def arg(
    delimiter: Delimiter | None = None,
    *,
    default: Any = dataclasses.MISSING,  # noqa: ANN401  # as dataclasses.field
    fill: str | Gap = Gap.UNDECLARED,
    sep: str | None = None,
    group: SlotGroup | None = None,
    booleans: tuple[str, str] | None = None,
    renamed_from: str | None = None,
    doc: str | None = None,
    meta: Mapping[str, object] | None = None,
    kw_only: bool = True,
) -> Any:  # noqa: ANN401  # as dataclasses.field
    """How a field is written as an argument. Give an optional field `default=None` (so a type checker knows it).

    `delimiter` defaults to `{}` for a required field and `[]` for an optional one (a field with a `default`). `fill`
    is the text between the delimiters written when this optional slot is unset while a later optional slot is set
    (`Gap.REFUSE` refuses that). `sep` separates the elements of a tuple or list (default `,`); `group` makes the field
    part of a `SlotGroup`; `booleans` is the literal pair of a `bool`. A field with a default is keyword-only in
    Python, wherever it stands among the others; a required field is positional."""
    notes = FieldNotes(renamed_from, doc, dict(meta or {}))
    return field_info(default, notes, ArgOptions(delimiter, fill, sep, group, booleans), kw_only=kw_only)


@enum.unique
class BodyKind(enum.Enum):
    TEXT = "Text"
    PDF = "PdfString"
    RAW = "Raw"
    CHOICE = "Choice"
    LENGTH = "Length"
    COLOUR = "Colour"
    COLOUR_NAME = "ColourName"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    TUPLE = "tuple"
    LIST = "list"
    KEYVALS = "KeyVals"
    TOKEN = "Token"
    TEX = "AsTeX"
    ONE_OF = "union"


@dataclasses.dataclass(frozen=True)
class Body:
    """What a slot holds, resolved from the field's type."""

    kind: BodyKind
    choice: type[Choice] | None = None
    items: tuple["Body", ...] = ()  # TUPLE: one per element; LIST: the one element; ONE_OF: the alternatives
    attrs: tuple[str, ...] = ()  # TUPLE of a record (NamedTuple, dataclass, model): the attributes in order
    keyvals: type | None = None
    token: str | None = None
    expression: type | tuple[type, ...] | None = (
        None  # RAW: the `Raw` subclass (or subclasses: a union) it must be; TEX: the type
    )

    def describe(self) -> str:
        if self.choice is not None:
            return f"one of {list(self.choice.__members__)}"
        if self.keyvals is not None:
            return self.keyvals.__name__
        if self.expression is not None:
            names = self.expression if isinstance(self.expression, tuple) else (self.expression,)
            return " | ".join(t.__name__ for t in names)
        if self.kind is BodyKind.ONE_OF:
            return " | ".join(i.describe() for i in self.items)
        if self.kind in (BodyKind.TUPLE, BodyKind.LIST):
            return f"{self.kind.value} of ({', '.join(i.describe() for i in self.items)})"
        return self.kind.value


RAW_BODY: Final = Body(BodyKind.RAW)
TEXT_BODY: Final = Body(BodyKind.TEXT)


__all__ = [
    "ANGLE",
    "ArgOptions",
    "BRACE",
    "Body",
    "BodyKind",
    "ColourName",
    "XCOLOR",
    "colour_of",
    "constraint_of",
    "Delimiter",
    "FLAG",
    "Flag",
    "Gap",
    "ITEM",
    "Item",
    "OptionalValue",
    "PAREN",
    "RAW_BODY",
    "SQUARE",
    "SWITCH",
    "SlotGroup",
    "Star",
    "Switch",
    "TEXT_BODY",
    "Token",
    "arg",
]
