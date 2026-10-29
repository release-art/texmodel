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
import types
import typing
from collections.abc import Mapping
from typing import Annotated, Any, Final, Literal

import pydantic
from pydantic.fields import FieldInfo
from pydantic_core import core_schema

from .errors import DeclarationError
from .types import CMYK, PDF, PROCESS, RGB, TEXT, Choice, Gray, Length, Plate, Raw, plain_number, plates_of


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
_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_CHARS = re.compile(r"[A-Za-z][A-Za-z0-9!.+-]*")


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
        if not _CHARS.fullmatch(text):
            raise DeclarationError(
                f"ColourName({text!r}): letters, digits and `!-.+` only, a letter first", code="TM-M067"
            )
        return super().__new__(cls, text)

    @property
    def names(self) -> tuple[str, ...]:
        """The colours the expression uses, in order; `TM-M067` if it is not `name(!number(!name)?)*`."""
        parts = self.split("!")
        names = parts[0::2]
        numbers = parts[1::2]
        if not all(_NAME.fullmatch(n) for n in names) or not all(
            _NUMBER.fullmatch(n) and float(n) <= 100 for n in numbers
        ):
            raise DeclarationError(
                f"ColourName({str(self)!r}): not `name`, `name!50` or `name!50!name`", code="TM-M067"
            )
        return tuple(names)

    @classmethod
    def __get_pydantic_core_schema__(cls, source: object, handler: Any) -> core_schema.CoreSchema:  # noqa: ANN401
        def make(value: str) -> "ColourName":
            try:
                found = cls(value)
                found.names  # noqa: B018  # the grammar is checked here too
            except DeclarationError as exc:
                raise ValueError(str(exc)) from exc
            return found

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


@dataclasses.dataclass(frozen=True)
class FieldNotes:
    """What `field()` and `arg()` say about a field besides its slot: its old name in data, its doc, its `x-` keys."""

    renamed_from: str | None = None
    doc: str | None = None
    meta: Mapping[str, object] = dataclasses.field(default_factory=dict[str, object])


def field_info(default: object, notes: FieldNotes, *more: object, kw_only: bool | None) -> FieldInfo:
    """A pydantic field carrying `notes` (and `more`, an `ArgOptions`) in its metadata; the schema shows the doc, the
    old name as `x-renamed-from` and the meta as `x-` keys. `dataclasses.MISSING` makes it required."""
    extra: dict[str, Any] = {f"x-{k}": v for k, v in notes.meta.items()}
    if notes.renamed_from is not None:
        extra = {"x-renamed-from": notes.renamed_from, **extra}
    given: dict[str, Any] = {} if default is dataclasses.MISSING else {"default": default}
    info: FieldInfo = pydantic.Field(**given, kw_only=kw_only, description=notes.doc, json_schema_extra=extra or None)
    info.metadata += [notes, *more]
    return info


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


@dataclasses.dataclass(frozen=True)
class Body:
    """What a slot holds, resolved from the field's type."""

    kind: BodyKind
    choice: type[Choice] | None = None
    items: tuple["Body", ...] = ()  # TUPLE: one per element; LIST: the one element
    attrs: tuple[str, ...] = ()  # TUPLE of a record (NamedTuple, dataclass, model): the attributes in order
    keyvals: type | None = None
    token: str | None = None
    expression: type | None = None  # RAW: a `Raw` subclass the value must be (an expression type of a library)

    def describe(self) -> str:
        if self.choice is not None:
            return f"one of {list(self.choice.__members__)}"
        if self.keyvals is not None:
            return self.keyvals.__name__
        if self.expression is not None:
            return self.expression.__name__
        if self.kind in (BodyKind.TUPLE, BodyKind.LIST):
            return f"{self.kind.value} of ({', '.join(i.describe() for i in self.items)})"
        return self.kind.value


RAW_BODY: Final = Body(BodyKind.RAW)
TEXT_BODY: Final = Body(BodyKind.TEXT)

_COLOURS = (CMYK, RGB, Gray)


def _members(hint: Any) -> list[Any]:  # noqa: ANN401
    """`X | None` as [X], `A | B` as [A, B]."""
    found = (
        typing.get_args(hint)
        if isinstance(hint, types.UnionType) or typing.get_origin(hint) is typing.Union
        else (hint,)
    )
    return [m for m in found if m is not type(None)]


def record_fields(tp: Any) -> list[tuple[str, Any]] | None:  # noqa: ANN401, PLR0911
    """The attributes and types of a NamedTuple, a dataclass or a pydantic model that is not a `KeyVals`, in order."""
    hints: dict[str, Any] = typing.get_type_hints(tp, include_extras=True)
    named = getattr(tp, "_fields", None)  # a NamedTuple
    if isinstance(named, tuple):
        return [(n, hints[n]) for n in typing.cast("tuple[str, ...]", named)]
    if dataclasses.is_dataclass(tp):
        return [(f.name, hints[f.name]) for f in dataclasses.fields(tp)]
    model_fields = getattr(tp, "model_fields", None)
    if isinstance(model_fields, dict):
        return [(n, hints[n]) for n in typing.cast("dict[str, object]", model_fields)]
    return None


def body_of(hint: Any) -> Body | None:  # noqa: ANN401, C901
    """The body a field annotation means, or None if it is no supported type. `X | None` is `X`."""
    members = _members(hint)
    if len(members) != 1:
        return _union_body(members)
    (h,) = members
    marks = typing.get_args(h)[1:] if typing.get_origin(h) is Annotated else ()
    inner = typing.get_args(h)[0] if marks else h
    simple = {TEXT: BodyKind.TEXT, PDF: BodyKind.PDF}
    for mark in marks:
        if mark in simple:
            return Body(simple[mark])
        if isinstance(mark, Token):
            return Body(BodyKind.TOKEN, token=mark.char)
    if marks:
        return body_of(inner)
    origin = typing.get_origin(h)
    if origin is Item or origin is OptionalValue:
        return body_of(typing.get_args(h)[0])
    if isinstance(h, type) and issubclass(h, ColourName):
        return Body(BodyKind.COLOUR_NAME)
    if h is Raw:
        return RAW_BODY
    if isinstance(h, type) and issubclass(h, Raw):
        return Body(BodyKind.RAW, expression=h)
    if h is bool:
        return Body(BodyKind.BOOL)
    if h is int:
        return Body(BodyKind.INT)
    if h is float:
        return Body(BodyKind.FLOAT)
    if isinstance(h, type) and issubclass(h, Length):
        return Body(BodyKind.LENGTH)
    if isinstance(h, type) and issubclass(h, Choice):
        return Body(BodyKind.CHOICE, choice=h)
    if isinstance(h, type) and getattr(h, "__tm_keyvals__", False):
        return Body(BodyKind.KEYVALS, keyvals=h)
    if origin is list:
        element = body_of(typing.get_args(h)[0])
        return None if element is None else Body(BodyKind.LIST, items=(element,))
    if origin is tuple:
        return _tuple_body(typing.get_args(h))
    if isinstance(h, type) and (fields := record_fields(h)) is not None:
        bodies = [body_of(t) for _, t in fields]
        if None in bodies:
            return None
        return Body(BodyKind.TUPLE, items=tuple(b for b in bodies if b is not None), attrs=tuple(n for n, _ in fields))
    return None


def _tuple_body(args: tuple[Any, ...]) -> Body | None:
    if len(args) == 2 and args[1] is Ellipsis:
        element = body_of(args[0])
        return None if element is None else Body(BodyKind.LIST, items=(element,))
    bodies = [body_of(a) for a in args]
    return (
        None if not bodies or None in bodies else Body(BodyKind.TUPLE, items=tuple(b for b in bodies if b is not None))
    )


def _union_body(members: list[Any]) -> Body | None:
    """The one union a field may be: the colour models (`Colour`)."""
    if members and set(members) == set(_COLOURS):
        return Body(BodyKind.COLOUR)
    return None


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
