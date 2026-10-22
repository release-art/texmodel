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
import types
import typing
from typing import Annotated, Any, Final, Literal

from .errors import DeclarationError
from .types import CMYK, PDF, RGB, TEXT, Choice, Gray, Length, Raw


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
COLOUR_NAME: Final = _Marker("ColourName")

Flag = Annotated[bool, FLAG]
"""A key of a `KeyVals` written bare when set: `center`."""
Switch = Annotated[bool, SWITCH]
"""A key of a `KeyVals` written with its boolean literal when set: `clip=true`. Declared `Switch | None = None`; `None`
leaves it out."""
ColourName = Annotated[str, COLOUR_NAME]
"""The name of a colour or an xcolor expression (`red`, `blue!50!black`): letters, digits and `!-.+` only."""
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
    kw_only: bool = True,
) -> Any:  # noqa: ANN401  # as dataclasses.field
    """How a field is written as an argument. Give an optional field `default=None` (so a type checker knows it).

    `delimiter` defaults to `{}` for a required field and `[]` for an optional one (a field with a `default`). `fill`
    is the text between the delimiters written when this optional slot is unset while a later optional slot is set
    (`Gap.REFUSE` refuses that). `sep` separates the elements of a tuple or list (default `,`); `group` makes the field
    part of a `SlotGroup`; `booleans` is the literal pair of a `bool`. A field with a default is keyword-only in
    Python, wherever it stands among the others; a required field is positional."""
    metadata: dict[str, object] = {"tm": ArgOptions(delimiter, fill, sep, group, booleans)}
    if renamed_from is not None:
        metadata["renamed_from"] = renamed_from
    return dataclasses.field(default=default, kw_only=kw_only, metadata=metadata)


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

    def describe(self) -> str:
        if self.choice is not None:
            return f"one of {list(self.choice.__members__)}"
        if self.keyvals is not None:
            return self.keyvals.__name__
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
    simple = {TEXT: BodyKind.TEXT, PDF: BodyKind.PDF, COLOUR_NAME: BodyKind.COLOUR_NAME}
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
    if h is Raw:
        return RAW_BODY
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
