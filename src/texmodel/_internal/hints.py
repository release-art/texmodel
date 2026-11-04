"""The `FieldType` a field annotation means: how a value of that type is checked, written and read as an argument."""

import dataclasses
import types
import typing
from collections.abc import Callable
from typing import Annotated, Any, cast

from ..interface import ColourName, Item, OptionalValue, Token
from ..types import CMYK, PDF, RGB, TEXT, AsTeX, Choice, Gray, Length, Raw
from .fieldtypes import (
    PDF_TYPE,
    RAW_TYPE,
    TEXT_TYPE,
    BoolType,
    ChoiceType,
    ColourNameType,
    ColourType,
    FieldType,
    FloatType,
    IntType,
    KeyList,
    LengthType,
    ListOf,
    OneOf,
    TokenType,
    TupleOf,
    Written,
)

_COLOURS = (CMYK, RGB, Gray)
_EXACT: dict[type, FieldType] = {Raw: RAW_TYPE, bool: BoolType(), int: IntType(), float: FloatType()}
_BY_BASE: tuple[tuple[type, Callable[[type[Any]], FieldType]], ...] = (  # a subclass of the first is its type
    (ColourName, lambda _: ColourNameType()),
    (Length, lambda _: LengthType()),
    (Choice, lambda h: ChoiceType(h)),
)


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


def type_of(hint: Any) -> FieldType | None:  # noqa: ANN401, C901, PLR0911
    """The type a field annotation means, or None if it is no supported type. `X | None` is `X`."""
    members = _members(hint)
    if len(members) != 1:
        return _union_type(members)
    (h,) = members
    marks = typing.get_args(h)[1:] if typing.get_origin(h) is Annotated else ()
    inner = typing.get_args(h)[0] if marks else h
    for mark in marks:
        if mark is TEXT:
            return TEXT_TYPE
        if mark is PDF:
            return PDF_TYPE
        if isinstance(mark, Token):
            return TokenType(mark.char)
    if marks:
        return type_of(inner)
    origin = typing.get_origin(h)
    if origin is Item or origin is OptionalValue:
        return type_of(typing.get_args(h)[0])
    if isinstance(h, type):
        return _class_type(cast("type[Any]", h))
    if origin is list:
        return _list_type(typing.get_args(h)[0])
    if origin is tuple:
        return _tuple_type(typing.get_args(h))
    return None


def _class_type(h: type[Any]) -> FieldType | None:
    if h in _EXACT:
        return _EXACT[h]
    for base, make in _BY_BASE:
        if issubclass(h, base):
            return make(h)
    if getattr(h, "__tm_keyvals__", False):
        return KeyList((cast("type[AsTeX]", h),))
    if issubclass(h, AsTeX):
        return Written((h,))
    if (fields := record_fields(h)) is None:
        return None
    types_ = [type_of(t) for _, t in fields]
    if None in types_:
        return None
    return TupleOf(tuple(t for t in types_ if t is not None), attrs=tuple(n for n, _ in fields))


def _list_type(element: Any) -> FieldType | None:  # noqa: ANN401
    item = type_of(element)
    return None if item is None else ListOf(item)


def _tuple_type(args: tuple[Any, ...]) -> FieldType | None:
    if len(args) == 2 and args[1] is Ellipsis:
        return _list_type(args[0])
    types_ = [type_of(a) for a in args]
    return None if not types_ or None in types_ else TupleOf(tuple(t for t in types_ if t is not None))


def _union_type(members: list[Any]) -> FieldType | None:
    """The unions a field may be: the colour models (`Colour`), several `Raw` subclasses (`FilePath | Macro`), or any
    types the field takes (`Icon | Picture`), each value written as the first alternative that holds it."""
    if members and set(members) == set(_COLOURS):
        return ColourType()
    if members and all(isinstance(m, type) and issubclass(m, Raw) for m in members):
        return Written(tuple(members))
    alternatives = [type_of(m) for m in members]
    if not members or None in alternatives:
        return None
    return OneOf(tuple(a for a in alternatives if a))
