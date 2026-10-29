"""Reading an argument back: the inverse of `value_text`, for the text TeX handed a stub (`\\detokenize`d: a space
after each control word, runs of spaces one)."""

import re

from ..errors import DeclarationError, Violation
from ..interface import Body, BodyKind
from ..plan import FieldEdit
from ..types import Length, Raw, escape
from .render import Arg
from .values import value_ok, value_text

_CONTROL_WORD = re.compile(r"\\[A-Za-z]+")
_INT = re.compile(r"-?\d+")
_FLOAT = re.compile(r"-?(\d+\.?\d*|\.\d+)")


def detokenized(tex: str) -> str:
    """`tex` as `\\detokenize` shows a macro argument: leading spaces gone, a run of spaces one, and a space after
    each control word (which also swallows the spaces that followed it)."""
    out: list[str] = []
    i, text = 0, tex.lstrip()
    while i < len(text):
        word = _CONTROL_WORD.match(text, i)
        if word:
            out.append(word[0] + " ")
            i = word.end()
        elif text[i] == "\\":
            out.append(text[i : i + 2])
            i += 2
        else:
            out.append(" " if text[i].isspace() else text[i])
            i += 1
        if out[-1].endswith(" "):  # after a control word or a space: further spaces are skipped
            while i < len(text) and text[i].isspace():
                i += 1
    return "".join(out)


_UNESCAPE = {detokenized(escape(c)): c for c in "\\&%$#_{}~^"}
_TEXT = re.compile("|".join(map(re.escape, sorted(_UNESCAPE, key=len, reverse=True))) + r"|[\\{}%$#&_^~]")


def _text(text: str) -> str:
    def one(m: re.Match[str]) -> str:
        if m[0] not in _UNESCAPE:
            raise ValueError(f"{m[0]!r} is TeX, not text")
        return _UNESCAPE[m[0]]

    return _TEXT.sub(one, text)


def _length(text: str) -> Length:
    try:
        return Length("".join(text.split()))
    except DeclarationError:
        if "\\" in text:
            return Length.expr(text.strip())
        raise ValueError(f"{text!r} is not a number with a unit, or a TeX length") from None


def read_value(body: Body, text: str, *, booleans: tuple[str, str] = ("true", "false"), sep: str = ",") -> object:  # noqa: C901
    """The value `text` is, for a slot that holds `body`; `ValueError` says why it is not one. `NotImplementedError`
    for what the text does not say (a colour's model, a key list, a PDF string, a `Raw` subclass)."""
    shown = text.strip()
    match body.kind:
        case BodyKind.TEXT:
            return _text(text)
        case BodyKind.RAW if body.expression is None:
            return Raw(text)
        case BodyKind.CHOICE if body.choice is not None:
            for member in body.choice:
                if detokenized(value_text(body, member)).strip() == shown:
                    return member
            raise ValueError(f"{shown!r} is not a {body.choice.__name__}")
        case BodyKind.LENGTH:
            return _length(text)
        case BodyKind.COLOUR_NAME:
            if not value_ok(body, shown):
                raise ValueError(f"{shown!r} is not a colour name")
            return shown
        case BodyKind.INT:
            if not _INT.fullmatch(shown):
                raise ValueError(f"{shown!r} is not an integer")
            return int(shown)
        case BodyKind.FLOAT:
            if not _FLOAT.fullmatch(shown):
                raise ValueError(f"{shown!r} is not a number")
            return float(shown)
        case BodyKind.BOOL:
            if shown not in booleans:
                raise ValueError(f"{shown!r} is not {booleans[0]} or {booleans[1]}")
            return shown == booleans[0]
        case BodyKind.TOKEN:
            if shown not in (r"\BooleanTrue", r"\BooleanFalse"):
                raise ValueError(f"{shown!r} is not a token flag")
            return shown == r"\BooleanTrue"
        case BodyKind.TUPLE:
            parts = text.split(sep)
            if len(parts) != len(body.items):
                raise ValueError(f"{shown!r} is not {len(body.items)} parts separated by {sep!r}")
            return tuple(read_value(b, p, booleans=booleans, sep=sep) for b, p in zip(body.items, parts, strict=True))
        case BodyKind.LIST:
            return [read_value(body.items[0], p, booleans=booleans, sep=sep) for p in text.split(sep)] if text else []
        case _:
            raise NotImplementedError(body.kind.value)


def read_field(a: Arg, text: str) -> FieldEdit:
    """One argument's text (as `\\detokenize` shows it) as a `FieldEdit`: the typed value it reads back to. An optional
    argument left out or empty has no value. A text that is not a value of the field's type has a `Violation`
    (`TM-C021`) whose path is the field; what the text cannot say (a colour's model, a key list) has neither."""
    if a.optional and not a.token and not text:
        return FieldEdit(a.name, text)
    try:
        return FieldEdit(a.name, text, read_value(a.body, text, booleans=a.booleans, sep=a.sep))
    except NotImplementedError:
        return FieldEdit(a.name, text)
    except ValueError as exc:
        hint = f"expected {a.body.describe()}"
        return FieldEdit(a.name, text, violation=Violation("TM-C021", a.name, f"{a.name}: {exc}", hint=hint))
