"""The `Body` a field annotation means: how a value of that type is checked and written as an argument."""

import dataclasses
import types
import typing
from typing import Annotated, Any

from ..interface import RAW_BODY, Body, BodyKind, ColourName, Item, OptionalValue, Token
from ..types import CMYK, PDF, RGB, TEXT, Choice, Gray, Length, Raw

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
    """The unions a field may be: the colour models (`Colour`), or several `Raw` subclasses (`FilePath | Macro`)."""
    if members and set(members) == set(_COLOURS):
        return Body(BodyKind.COLOUR)
    if members and all(isinstance(m, type) and issubclass(m, Raw) for m in members):
        return Body(BodyKind.RAW, expression=tuple(members))
    return None
