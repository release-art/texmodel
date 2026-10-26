"""What a slot's value is and how it is written: checking a value against its `Body`
and turning it into TeX."""

import dataclasses
import re
from collections.abc import Mapping
from typing import Any, cast

from ..body import Syntax, text_of
from ..errors import DeclarationError
from ..interface import Body, BodyKind
from ..types import CMYK, RGB, Gray, Length, Raw, pdf_escape, plain_number

_COLOUR_NAME = re.compile(r"[A-Za-z][A-Za-z0-9!.+-]*")


def unprotected(text: str, chars: str) -> bool:
    """Whether any of `chars` stands in `text` outside braces and outside a control sequence's own character: the place
    a delimiter or separator would be read."""
    depth, i = 0, 0
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        depth += c == "{"
        depth -= c == "}"
        if depth == 0 and c in chars:
            return True
        i += 1
    return False


def elements(body: Body, value: Any) -> list[Any]:  # noqa: ANN401
    """The parts of a tuple value, in order: a plain tuple's items, or a record's attributes."""
    return [getattr(value, a) for a in body.attrs] if body.attrs else list(value)


def value_ok(body: Body, value: Any) -> bool:  # noqa: ANN401, C901
    """Whether `value` is what the slot holds."""
    match body.kind:
        case BodyKind.TEXT | BodyKind.PDF:
            return isinstance(value, str)
        case BodyKind.COLOUR_NAME:
            return isinstance(value, str) and bool(_COLOUR_NAME.fullmatch(value))
        case BodyKind.RAW:
            return isinstance(value, body.expression or Raw)
        case BodyKind.CHOICE:
            return body.choice is not None and isinstance(value, body.choice)
        case BodyKind.LENGTH:
            return isinstance(value, Length)
        case BodyKind.COLOUR:
            return isinstance(value, CMYK | RGB | Gray)
        case BodyKind.INT:
            return type(value) is int
        case BodyKind.FLOAT:
            return isinstance(value, int | float) and not isinstance(value, bool)
        case BodyKind.BOOL | BodyKind.TOKEN:
            return isinstance(value, bool)
        case BodyKind.KEYVALS:
            return body.keyvals is not None and isinstance(value, body.keyvals)
        case BodyKind.LIST:
            return isinstance(value, list | tuple) and all(value_ok(body.items[0], v) for v in cast("list[Any]", value))
        case BodyKind.TUPLE:
            if body.attrs:
                return all(hasattr(value, a) for a in body.attrs) and all(
                    value_ok(b, v) for b, v in zip(body.items, elements(body, value), strict=True)
                )
            return (
                isinstance(value, tuple)
                and len(cast("tuple[Any, ...]", value)) == len(body.items)
                and all(value_ok(b, v) for b, v in zip(body.items, cast("tuple[Any, ...]", value), strict=True))
            )


def value_text(  # noqa: C901
    body: Body,
    value: Any,  # noqa: ANN401
    syntax: Syntax = Syntax.LATEX2E,
    *,
    booleans: tuple[str, str] = ("true", "false"),
    sep: str = ",",
) -> str:
    """The TeX of a value, without its delimiters: `Text` escaped (a space is `~` in expl3), `Raw` as it is."""
    match body.kind:
        case BodyKind.TEXT:
            return text_of(str(value), syntax)
        case BodyKind.PDF:
            pdf = f"\\detokenize{{{pdf_escape(str(value))}}}"
            return pdf.replace(" ", "~") if syntax is Syntax.EXPL3 else pdf
        case BodyKind.RAW:
            return value.tex
        case BodyKind.CHOICE:
            member = value.value
            return member.tex if isinstance(member, Raw) else text_of(str(member), syntax)
        case BodyKind.BOOL:
            return booleans[0 if value else 1]
        case BodyKind.TOKEN:
            return (body.token or "") if value else ""
        case BodyKind.KEYVALS:
            return value.render()
        case BodyKind.LIST:
            return sep.join(value_text(body.items[0], v, syntax, booleans=booleans, sep=sep) for v in value)
        case BodyKind.TUPLE:
            parts = elements(body, value)
            return sep.join(
                value_text(b, v, syntax, booleans=booleans, sep=sep) for b, v in zip(body.items, parts, strict=True)
            )
        case BodyKind.FLOAT:
            return plain_number(value)
        case BodyKind.LENGTH | BodyKind.COLOUR | BodyKind.COLOUR_NAME | BodyKind.INT:
            return str(value)


_MODEL_HOLE = re.compile(r"<<(?P<path>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)>>")


def _member(holder: object, name: str) -> object:
    """A field of a mapping, a dataclass or a pydantic model; `KeyError` if it has none."""
    if isinstance(holder, Mapping):
        return cast("Mapping[str, object]", holder)[name]
    fields = (
        {f.name for f in dataclasses.fields(holder)}
        if dataclasses.is_dataclass(holder)
        else set(getattr(type(holder), "model_fields", ()))
    )
    if name in fields:
        return getattr(holder, name)
    raise KeyError(name)


def hole_text(value: object, syntax: Syntax) -> str:
    """The TeX of a value that fills a hole: `str` is text (escaped), `Raw` as it is, a length, a colour model, a number
    or a flag as it is written. Any other type is refused, so a hole never gets an unescaped surprise."""
    match value:
        case Raw():
            return value.tex
        case bool():
            return "true" if value else "false"
        case str():
            return text_of(value, syntax)
        case int():
            return str(value)
        case float():
            return plain_number(value)
        case Length() | CMYK() | RGB() | Gray():
            return str(value)
        case _:
            raise DeclarationError(
                f"a hole cannot take a {type(value).__name__}",
                code="TM-M040",
                hint="fill it with str (text), Raw (TeX), Length, a colour model, int, float or bool",
            )


def fill_text(text: str, model: object, syntax: Syntax, owner: str) -> str:
    """`text` with every `<<name>>` (or `<<a.b>>` into a nested model) replaced by the model's value (§21). `model`
    is a mapping, a dataclass or a pydantic model; a hole it has no field for is an error (`TM-M041`). A model may hold
    more than one part uses."""

    def sub(m: re.Match[str]) -> str:
        value: object = model
        try:
            for name in m["path"].split("."):
                value = _member(value, name)
        except (KeyError, TypeError) as exc:
            raise DeclarationError(
                f"{owner}: the model has no {m['path']!r} for the hole {m[0]}",
                code="TM-M041",
                hint="name a field of the model; nested fields are written a.b",
            ) from exc
        return hole_text(value, syntax)

    return _MODEL_HOLE.sub(sub, text)
