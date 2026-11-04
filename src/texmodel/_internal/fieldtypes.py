"""What a field holds: one `FieldType` per kind of value, each saying how a value is checked (`ok`), written (`text`)
and read back from a stub call (`read`). A type is data the renderer calls, never a branch in it; `AsTeX` is how a user
adds one (`Written`). `type_of` in `hints.py` is the type a field annotation means."""

import abc
import dataclasses
import re
from typing import Any, ClassVar, cast

from ..body import Syntax
from ..errors import DeclarationError
from ..types import CMYK, RGB, AsTeX, Choice, Gray, Length, Raw, escape, pdf_escape, plain_number
from .inline import text_of
from .tex import detokenized

_COLOUR_NAME = re.compile(r"[A-Za-z\\][A-Za-z0-9!.+@\\-]*")
_INT = re.compile(r"-?\d+")
_FLOAT = re.compile(r"-?(\d+\.?\d*|\.\d+)")
_UNESCAPE = {detokenized(escape(c)): c for c in "\\&%$#_{}~^"}
_TEXT = re.compile("|".join(map(re.escape, sorted(_UNESCAPE, key=len, reverse=True))) + r"|[\\{}%$#&_^~]")
TRUE_TOKEN, FALSE_TOKEN = r"\BooleanTrue", r"\BooleanFalse"


def unescaped(text: str) -> str:
    """The text `text` writes, the inverse of `escape`; `ValueError` for TeX that is not text."""

    def one(m: re.Match[str]) -> str:
        if m[0] not in _UNESCAPE:
            raise ValueError(f"{m[0]!r} is TeX, not text")
        return _UNESCAPE[m[0]]

    return _TEXT.sub(one, text)


def read_length(text: str) -> Length:
    try:
        return Length("".join(text.split()))
    except DeclarationError:
        if "\\" in text:
            return Length.expr(text.strip())
        raise ValueError(f"{text!r} is not a number with a unit, or a TeX length") from None


@dataclasses.dataclass(frozen=True)
class Style:
    """How an argument writes and reads its values: the syntax its text is escaped for, the literals of a `bool`, the
    separator of a tuple or list."""

    syntax: Syntax = Syntax.LATEX2E
    booleans: tuple[str, str] = ("true", "false")
    sep: str = ","


PLAIN = Style()


@dataclasses.dataclass(frozen=True)
class FieldType(abc.ABC):
    """A kind of value a field holds."""

    name: ClassVar[str]  # how a violation names it
    is_token: ClassVar[bool] = False  # a bare character in the call, not an argument
    key_list: ClassVar[bool] = False  # a `KeyVals`: written between a delimiter pair, empty means unset
    nests_calls: ClassVar[bool] = False  # may hold calls (a `Ref` or `Seq`), not only text
    defaultable: ClassVar[bool] = True  # has a one-argument form to default (`\newcommand`'s `[default]`)

    @abc.abstractmethod
    def ok(self, value: object) -> bool:
        """Whether `value` is what the field holds."""

    @abc.abstractmethod
    def text(self, value: object, style: Style = PLAIN) -> str:
        """The TeX of `value`, without its delimiters."""

    def read(self, text: str, style: Style = PLAIN) -> object:
        """The value `text` is (as `\\detokenize` shows it); `ValueError` says why it is not one, and
        `NotImplementedError` that the text does not say (a colour's model, a key list, a PDF string)."""
        raise NotImplementedError(self.describe())

    def describe(self) -> str:
        return self.name


@dataclasses.dataclass(frozen=True)
class TextType(FieldType):
    name: ClassVar[str] = "Text"

    def ok(self, value: object) -> bool:
        return isinstance(value, str)

    def text(self, value: object, style: Style = PLAIN) -> str:
        return text_of(str(value), style.syntax)

    def read(self, text: str, style: Style = PLAIN) -> object:
        return unescaped(text)


@dataclasses.dataclass(frozen=True)
class PdfType(FieldType):
    """A PDF string: written by `\\detokenize`, so it is not escaped as text, and not read back."""

    name: ClassVar[str] = "PdfString"

    def ok(self, value: object) -> bool:
        return isinstance(value, str)

    def text(self, value: object, style: Style = PLAIN) -> str:
        pdf = f"\\detokenize{{{pdf_escape(str(value))}}}"
        return pdf.replace(" ", "~") if style.syntax is Syntax.EXPL3 else pdf


@dataclasses.dataclass(frozen=True)
class ColourNameType(FieldType):
    name: ClassVar[str] = "ColourName"

    def ok(self, value: object) -> bool:
        return isinstance(value, str) and bool(_COLOUR_NAME.fullmatch(value))

    def text(self, value: object, style: Style = PLAIN) -> str:
        return str(value)

    def read(self, text: str, style: Style = PLAIN) -> object:
        shown = text.strip()
        if not self.ok(shown):
            raise ValueError(f"{shown!r} is not a colour name")
        return shown


@dataclasses.dataclass(frozen=True)
class LengthType(FieldType):
    name: ClassVar[str] = "Length"

    def ok(self, value: object) -> bool:
        return isinstance(value, Length)

    def text(self, value: object, style: Style = PLAIN) -> str:
        return str(value)

    def read(self, text: str, style: Style = PLAIN) -> object:
        return read_length(text)


@dataclasses.dataclass(frozen=True)
class ColourType(FieldType):
    """One of the colour models; the text is the model's own, so reading it back cannot say which."""

    name: ClassVar[str] = "Colour"

    def ok(self, value: object) -> bool:
        return isinstance(value, CMYK | RGB | Gray)

    def text(self, value: object, style: Style = PLAIN) -> str:
        return str(value)


@dataclasses.dataclass(frozen=True)
class IntType(FieldType):
    name: ClassVar[str] = "int"

    def ok(self, value: object) -> bool:
        return type(value) is int

    def text(self, value: object, style: Style = PLAIN) -> str:
        return str(value)

    def read(self, text: str, style: Style = PLAIN) -> object:
        shown = text.strip()
        if not _INT.fullmatch(shown):
            raise ValueError(f"{shown!r} is not an integer")
        return int(shown)


@dataclasses.dataclass(frozen=True)
class FloatType(FieldType):
    name: ClassVar[str] = "float"

    def ok(self, value: object) -> bool:
        return isinstance(value, int | float) and not isinstance(value, bool)

    def text(self, value: object, style: Style = PLAIN) -> str:
        return plain_number(cast("float", value))

    def read(self, text: str, style: Style = PLAIN) -> object:
        shown = text.strip()
        if not _FLOAT.fullmatch(shown):
            raise ValueError(f"{shown!r} is not a number")
        return float(shown)


@dataclasses.dataclass(frozen=True)
class BoolType(FieldType):
    name: ClassVar[str] = "bool"

    def ok(self, value: object) -> bool:
        return isinstance(value, bool)

    def text(self, value: object, style: Style = PLAIN) -> str:
        return style.booleans[0 if value else 1]

    def read(self, text: str, style: Style = PLAIN) -> object:
        shown = text.strip()
        if shown not in style.booleans:
            raise ValueError(f"{shown!r} is not {style.booleans[0]} or {style.booleans[1]}")
        return shown == style.booleans[0]


@dataclasses.dataclass(frozen=True)
class TokenType(FieldType):
    """A flag written as one character after the command name (`Star`): `True` writes it, `False` leaves it out."""

    char: str
    name: ClassVar[str] = "Token"
    is_token: ClassVar[bool] = True
    defaultable: ClassVar[bool] = False

    def ok(self, value: object) -> bool:
        return isinstance(value, bool)

    def text(self, value: object, style: Style = PLAIN) -> str:
        return self.char if value else ""

    def read(self, text: str, style: Style = PLAIN) -> object:
        shown = text.strip()
        if shown not in (TRUE_TOKEN, FALSE_TOKEN):
            raise ValueError(f"{shown!r} is not a token flag")
        return shown == TRUE_TOKEN


@dataclasses.dataclass(frozen=True)
class ChoiceType(FieldType):
    """A member of a `Choice`, written as its value: `Text` (escaped) or `Raw` (as it is)."""

    choice: type[Choice]
    name: ClassVar[str] = "Choice"

    def ok(self, value: object) -> bool:
        return isinstance(value, self.choice)

    def text(self, value: object, style: Style = PLAIN) -> str:
        member = cast("Choice", value).value
        return member.tex if isinstance(member, Raw) else text_of(str(member), style.syntax)

    def read(self, text: str, style: Style = PLAIN) -> object:
        shown = text.strip()
        for member in self.choice:
            if detokenized(self.text(member)).strip() == shown:
                return member
        raise ValueError(f"{shown!r} is not a {self.choice.__name__}")

    def describe(self) -> str:
        return f"one of {list(self.choice.__members__)}"


@dataclasses.dataclass(frozen=True)
class Written(FieldType):
    """An instance of a class that writes itself (`AsTeX`): `Raw` and its checked subclasses, a `KeyVals`, a user's own.
    Several classes (`FilePath | Macro`) are a union of `Raw`s. Only a class that reads itself (`from_tex`) is read
    back, and a union is not."""

    classes: tuple[type[AsTeX], ...]
    name: ClassVar[str] = "AsTeX"

    @property
    def verbatim(self) -> bool:
        """Whether it is TeX written as it is (`Raw`), which a key list takes as it stands."""
        return all(issubclass(c, Raw) for c in self.classes)

    def ok(self, value: object) -> bool:
        return isinstance(value, self.classes)

    def text(self, value: object, style: Style = PLAIN) -> str:
        return cast("AsTeX", value).render()

    def read(self, text: str, style: Style = PLAIN) -> object:
        if len(self.classes) != 1:
            raise NotImplementedError(self.describe())
        return self.classes[0].from_tex(text)

    def describe(self) -> str:
        return " | ".join(c.__name__ for c in self.classes)


@dataclasses.dataclass(frozen=True)
class AnyRaw(Written):
    """`Raw` itself: any TeX, which reads back as it is and may hold calls."""

    nests_calls: ClassVar[bool] = True

    def read(self, text: str, style: Style = PLAIN) -> object:
        return Raw(text)


@dataclasses.dataclass(frozen=True)
class KeyList(Written):
    """A `KeyVals`: written between a delimiter pair, whose closing delimiter its own braces may protect."""

    key_list: ClassVar[bool] = True
    defaultable: ClassVar[bool] = False


@dataclasses.dataclass(frozen=True)
class ListOf(FieldType):
    item: FieldType
    name: ClassVar[str] = "list"
    defaultable: ClassVar[bool] = False

    def ok(self, value: object) -> bool:
        return isinstance(value, list | tuple) and all(self.item.ok(v) for v in cast("list[object]", value))

    def text(self, value: object, style: Style = PLAIN) -> str:
        return style.sep.join(self.item.text(v, style) for v in cast("list[object]", value))

    def read(self, text: str, style: Style = PLAIN) -> object:
        return [self.item.read(p, style) for p in text.split(style.sep)] if text else []

    def describe(self) -> str:
        return f"{self.name} of ({self.item.describe()})"


@dataclasses.dataclass(frozen=True)
class TupleOf(FieldType):
    """A fixed number of parts: a plain tuple, or a record whose `attrs` name its attributes in order."""

    items: tuple[FieldType, ...]
    attrs: tuple[str, ...] = ()
    name: ClassVar[str] = "tuple"
    defaultable: ClassVar[bool] = False

    def _parts(self, value: object) -> list[Any]:
        return [getattr(value, a) for a in self.attrs] if self.attrs else list(cast("tuple[Any, ...]", value))

    def _shaped(self, value: object) -> bool:
        if self.attrs:
            return all(hasattr(value, a) for a in self.attrs)
        return isinstance(value, tuple) and len(cast("tuple[Any, ...]", value)) == len(self.items)

    def ok(self, value: object) -> bool:
        return self._shaped(value) and all(t.ok(v) for t, v in zip(self.items, self._parts(value), strict=True))

    def text(self, value: object, style: Style = PLAIN) -> str:
        return style.sep.join(t.text(v, style) for t, v in zip(self.items, self._parts(value), strict=True))

    def read(self, text: str, style: Style = PLAIN) -> object:
        parts = text.split(style.sep)
        if len(parts) != len(self.items):
            raise ValueError(f"{text.strip()!r} is not {len(self.items)} parts separated by {style.sep!r}")
        return tuple(t.read(p, style) for t, p in zip(self.items, parts, strict=True))

    def describe(self) -> str:
        return f"{self.name} of ({', '.join(t.describe() for t in self.items)})"


@dataclasses.dataclass(frozen=True)
class OneOf(FieldType):
    """Any of several types; a value is written as the first alternative that holds it."""

    items: tuple[FieldType, ...]
    name: ClassVar[str] = "union"

    def ok(self, value: object) -> bool:
        return any(t.ok(value) for t in self.items)

    def text(self, value: object, style: Style = PLAIN) -> str:
        return next(t for t in self.items if t.ok(value)).text(value, style)

    def read(self, text: str, style: Style = PLAIN) -> object:
        unread, refused = False, list[str]()
        for alternative in self.items:
            try:
                return alternative.read(text, style)
            except NotImplementedError:
                unread = True
            except ValueError as exc:
                refused.append(str(exc))
        if unread:  # one alternative may be what the text says, and cannot be read
            raise NotImplementedError(self.describe())
        raise ValueError(" and ".join(refused))

    def describe(self) -> str:
        return " | ".join(t.describe() for t in self.items)


TEXT_TYPE = TextType()
PDF_TYPE = PdfType()
RAW_TYPE = AnyRaw((Raw,))
