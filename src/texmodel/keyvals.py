r"""Key lists: the `key=value, flag, ...` argument of `\adjustbox`, `\includegraphics`,
`tikzpicture`, `\usepackage`.

A `KeyVals` is a frozen pydantic model. A field's type says how its item is written, its name (or `key("...")`) is the
key, and the class takes the `KeyRules` of the library that reads the list:

```python
class AdjustOptions(KeyVals, rules=PGFKEYS):
    max_width: Length | None = key("max width")     # max width=3cm
    center: Flag = False                           # center
    clip: Switch = None                            # clip=true / clip=false
    valign: VAlign | None = None                   # valign=top (a Choice)
    arrow: Item[Arrow] | None = None               # ->   (no key)
    rounded: OptionalValue[Length] | None = None   # rounded corners  /  rounded corners=2pt
    style: Inner | None = None                     # style={draw=red}  (another KeyVals)
    extra: Item[Raw] | None = None                 # anything else, as written
```

Items are written in declaration order and an unset one is left out. A `list[...]` field repeats its item.
"""

import dataclasses
import enum
import types
import typing
from typing import Any, ClassVar, cast

import pydantic

from ._internal.values import unprotected, value_text
from .errors import DeclarationError
from .interface import FLAG, SWITCH, Body, BodyKind, Item, OptionalValue, body_of
from .keys import KeyRules


@enum.unique
class ItemKind(enum.Enum):
    FLAG = "flag"  # `center`, when set
    SWITCH = "switch"  # `clip=true` / `clip=false`, when not None
    VALUE = "value"  # `max width=3cm`
    OPTIONAL_VALUE = "optional value"  # `rounded corners`, or `rounded corners=2pt`
    BARE = "bare"  # the value alone
    NESTED = "nested"  # `style={draw=red}`


@dataclasses.dataclass(frozen=True)
class KeyItem:
    name: str  # the field
    key: str  # as TeX spells it
    kind: ItemKind
    body: Body | None
    repeated: bool = False


def key(spelling: str | None = None, *, default: Any = None) -> Any:  # noqa: ANN401  # as pydantic.Field
    """The TeX spelling of a key whose field name cannot be it (`max_width` is `max width` by default; `line-width`
    needs `key("line-width")`). `default` is the Python default of the field."""
    return pydantic.Field(default=default, json_schema_extra={"x-tex-key": spelling} if spelling else None)


def _strip_none(hint: Any) -> list[Any]:  # noqa: ANN401
    found = (
        typing.get_args(hint)
        if isinstance(hint, types.UnionType) or typing.get_origin(hint) is typing.Union
        else (hint,)
    )
    return [m for m in found if m is not type(None)]


def _classify(cls: type, name: str, spelling: str, hint: Any, rules: KeyRules) -> KeyItem:  # noqa: ANN401, C901
    where = f"{cls.__qualname__}.{name}"

    def refuse(why: str, hint_text: str = "") -> DeclarationError:
        return DeclarationError(f"{where}: {why}", code="TM-M004", path=f"{cls.__name__}.{name}", hint=hint_text)

    members = _strip_none(hint)
    h: Any = hint if len(members) > 1 and body_of(hint) is not None else None
    if h is None:
        if len(members) != 1:
            raise refuse(f"unsupported type {hint!r}", "use one type, optionally | None")
        (h,) = members
    repeated = typing.get_origin(h) is list
    if repeated:
        inner_members = _strip_none(typing.get_args(h)[0])
        if len(inner_members) != 1:
            raise refuse(f"unsupported list element {typing.get_args(h)[0]!r}")
        (h,) = inner_members
    origin = typing.get_origin(h)
    marks = typing.get_args(h)[1:] if origin is typing.Annotated else ()
    if FLAG in marks or SWITCH in marks:
        if repeated:
            raise refuse("a Flag or Switch cannot repeat")
        return KeyItem(name, spelling, ItemKind.FLAG if FLAG in marks else ItemKind.SWITCH, None)
    kind, inner = ItemKind.VALUE, h
    if origin is Item:
        kind, inner = ItemKind.BARE, typing.get_args(h)[0]
    elif origin is OptionalValue:
        if repeated:
            raise refuse("an optional-value key cannot repeat")
        kind, inner = ItemKind.OPTIONAL_VALUE, typing.get_args(h)[0]
    body = body_of(inner)
    if body is None:
        raise refuse(
            f"unsupported type {inner!r}",
            "use Text, Raw, Length, Colour, int, a Choice, a tuple or list, another KeyVals, "
            "or Flag, Switch, Item[...]",
        )
    if body.kind is BodyKind.BOOL:
        raise refuse("a plain bool is ambiguous", "use Flag (the bare key) or Switch (key=true / key=false)")
    if body.kind is BodyKind.KEYVALS:
        if kind is not ItemKind.VALUE:
            raise refuse("a key list is a value of a key, not an item or optional value")
        if not rules.nesting:
            raise refuse("these KeyRules do not allow a key list as a value", "use rules that set nesting=True")
        kind = ItemKind.NESTED
    if body.kind is BodyKind.TOKEN:
        raise refuse("a Token belongs to a component's slots, not a key list")
    return KeyItem(name, spelling, kind, body, repeated)


class KeyVals(pydantic.BaseModel):
    """The base of a key list; give each subclass its library's `KeyRules`: `class Opts(KeyVals, rules=PGFKEYS)`.

    `exclusive` lists groups of fields of which at most one may be set; `requires` maps a field to the one it needs."""

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    __tm_keyvals__: ClassVar[bool] = True
    __tm_rules__: ClassVar[KeyRules]
    __tm_items__: ClassVar[tuple[KeyItem, ...]] = ()
    exclusive: ClassVar[tuple[tuple[str, ...], ...]] = ()
    requires: ClassVar[dict[str, str]] = {}

    def __init_subclass__(cls, *, rules: KeyRules | None = None, **kwargs: Any) -> None:  # noqa: ANN401
        super().__init_subclass__(**kwargs)
        if rules is not None:
            cls.__tm_rules__ = rules
        elif not hasattr(cls, "__tm_rules__"):
            raise DeclarationError(
                f"{cls.__qualname__}: say which library reads it",
                code="TM-M036",
                path=cls.__name__,
                hint="class Opts(KeyVals, rules=PGFKEYS) (see texmodel.keys)",
            )

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:  # noqa: ANN401
        super().__pydantic_init_subclass__(**kwargs)
        hints = typing.get_type_hints(cls, include_extras=True)
        items: list[KeyItem] = []
        for name, info in cls.model_fields.items():
            given: object = info.json_schema_extra
            extra = typing.cast("dict[str, Any]", given) if isinstance(given, dict) else {}
            spelling = extra.get("x-tex-key")
            items.append(_classify(cls, name, str(spelling or name.replace("_", " ")), hints[name], cls.__tm_rules__))
        cls.__tm_items__ = tuple(items)
        known = set(cls.model_fields)
        for names in cls.exclusive:
            if not set(names) <= known or len(names) < 2:
                raise DeclarationError(
                    f"{cls.__qualname__}: exclusive {names!r} names fields that are not there", code="TM-M004"
                )
        for needing, needed in cls.requires.items():
            if {needing, needed} - known:
                raise DeclarationError(
                    f"{cls.__qualname__}: requires {needing!r}: {needed!r} names a field that is not there",
                    code="TM-M004",
                )

    @pydantic.model_validator(mode="after")
    def _check_relations(self) -> "KeyVals":
        def given(name: str) -> bool:
            value = getattr(self, name)
            return value is not None and value is not False and value != []

        for names in self.exclusive:
            if len(chosen := [n for n in names if given(n)]) > 1:
                raise ValueError(f"at most one of {list(names)} may be set, got {chosen}")
        for needing, needed in self.requires.items():
            if given(needing) and not given(needed):
                raise ValueError(f"{needing} needs {needed}")
        return self

    def render(self) -> str:
        r"""The list as TeX, `max width=3cm,center`: items in declaration order, unset ones left out."""
        rules = type(self).__tm_rules__
        parts: list[str] = []
        for item in type(self).__tm_items__:
            parts += _parts(item, getattr(self, item.name), rules)
        return rules.separator.join(parts)


def _protected(text: str, rules: KeyRules, body: Body) -> str:
    """A value the library would split at a comma, an equals sign or a closing bracket is put in braces, as is an
    empty one. A space at an end is stripped by every library unless the value is in two pairs of braces (and for a
    library that trims whatever it is given, `KeyRules.edge_spaces`, it is left as it is). A `Raw` is as written."""
    if body.kind is BodyKind.RAW:
        return f"{{{text}}}" if rules.braced else text
    if text != text.strip() and rules.edge_spaces:
        return f"{{{{{text}}}}}"
    if rules.braced or not text or unprotected(text, f"{rules.separator}{rules.assign}]"):
        return f"{{{text}}}"
    return text


def _parts(item: KeyItem, value: Any, rules: KeyRules) -> list[str]:  # noqa: ANN401
    if value is None or value is False and item.kind is not ItemKind.SWITCH:
        return []
    k = item.key + rules.assign
    match item.kind:
        case ItemKind.FLAG:
            return [item.key]
        case ItemKind.SWITCH:
            return [k + rules.booleans[0 if value else 1]]
        case ItemKind.OPTIONAL_VALUE if value is True:
            return [item.key]
        case _:
            pass
    assert item.body is not None
    values: list[Any] = list(cast("list[Any]", value)) if item.repeated else [value]
    out: list[str] = []
    for v in values:
        text = value_text(item.body, v, booleans=rules.booleans)
        match item.kind:
            case ItemKind.BARE:
                out.append(_protected(text, rules, item.body))
            case ItemKind.NESTED:
                out.append(f"{k}{{{text}}}")
            case _:
                out.append(k + _protected(text, rules, item.body))
    return out


__all__ = ["ItemKind", "KeyItem", "KeyVals", "key"]
