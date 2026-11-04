"""Writing values as TeX: what a hole is filled with, and where a delimiter would be read in written text."""

import dataclasses
import re
from collections.abc import (
    Mapping,
    Set as AbstractSet,
)
from typing import cast

from ..body import Syntax
from ..errors import DeclarationError
from ..types import CMYK, RGB, Gray, Length, Raw, plain_number, plates_of
from .inline import text_of


def plates_outside(allowed: AbstractSet[str] | None, colour: object) -> str | None:
    """Why `colour` inks plates outside a value's `plates` (`TM-M070`); None when it does not or there are none."""
    if allowed is None or not (extra := plates_of(colour) - allowed):
        return None
    return f"inks {sorted(extra)}, outside {sorted(allowed)}"


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
