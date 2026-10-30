"""Typed settings, and the colour argument that names one."""

import typing
from collections.abc import (
    Mapping,
    Set as AbstractSet,
)
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

import pydantic

from .._internal.render import (
    BOOL,
    COLOUR,
    LENGTH,
    RAW_KIND,
    TEXT_KIND,
    check_name,
)
from .._internal.values import plates_outside
from ..body import (
    Cs,
    Library,
    Syntax,
)
from ..errors import DeclarationError
from ..interface import (
    ColourName,
)
from ..types import TEXT, Colour, Length, Raw, ValueKind

if TYPE_CHECKING:
    from ..package import Package


def colour_named(value: object) -> object:
    """A colour value class as its xcolor name (`ColourName(Ink)`); anything else as it is."""
    return ColourName(value) if isinstance(value, type) else value


if TYPE_CHECKING:  # a type checker sees the class too; at run time the field holds the name
    type ColourRef = ColourName | type[Value[Any]]
else:
    ColourRef = Annotated[ColourName, pydantic.BeforeValidator(colour_named)]
"""A colour argument: a `ColourName`, or a registered colour value (`bg=Ink`), which is stored as its name."""


def document_of(cls: type) -> str:
    """The docstring of a component, which must be documented and named as a TeX control word would be."""
    check_name(cls.__name__, "component")
    doc = (cls.__dict__.get("__doc__") or "").strip()
    if not doc:
        raise DeclarationError(f"{cls.__qualname__}: document the component in its docstring", code="TM-M002")
    return doc


_KINDS: dict[object, ValueKind] = {Length: LENGTH, Colour: COLOUR, bool: BOOL, str: TEXT_KIND, Raw: RAW_KIND}


def _check_plates(cls: "type[Value[Any]]", kind: ValueKind, default: object) -> None:
    """A colour value's `plates`: only a colour has them, and its default stays inside them (`TM-M069`, `TM-M070`)."""
    if (declared := cls.__dict__.get("plates")) is None:
        return
    if not kind.named:
        raise DeclarationError(
            f"{cls.__qualname__}: plates belongs to a colour value", code="TM-M069", path=cls.__name__
        )
    cls.plates = frozenset(declared)
    if default is not None and (why := plates_outside(cls.plates, default)):
        raise DeclarationError(f"{cls.__qualname__}: the default {why}", code="TM-M070", path=cls.__name__)


class Value[T]:
    """A typed setting: `\\newlength`, `\\definecolor`, `\\newif`, `\\newcommand` or a package's own (`Toggle`), chosen
    by `T`; `default` is an instance of `T`. A `Value[Text]` of an adopted package may leave `default` out: the
    hand-written package has it; so may a `Value[Length]` the package computes later. `colour_name` renames a colour."""

    default: T  # not ClassVar[T]: pyright refuses type variables in ClassVar; subclasses assign it in the class body
    needs_packages: ClassVar[tuple["str | Package", ...]] = ()  # data, not mutation: the package takes the union (M14)
    colour_name: ClassVar[str | None] = None  # a `Value[Colour]`'s name when it is not `<prefix>-<kebab>` (`"acInk"`)
    xcolor_name: ClassVar[
        ColourName
    ]  # a colour's resolved xcolor name, once registered: `colour_name` or `<prefix>-<kebab>`
    cs: ClassVar[str | None] = None  # the whole control sequence, when it is not prefix + class name (`"acshowcrop"`)
    defined_by: ClassVar[Library | None] = None  # the library block that defines it, so it renders no definition
    plates: ClassVar[AbstractSet[str] | None] = None  # a colour's plates: the set it may ink, `{Plate.K}` is K-only
    meta: ClassVar[Mapping[str, object]] = {}  # the schema's `x-` keys on this value
    __tm_doc__: ClassVar[str]
    __tm_kind__: ClassVar[ValueKind]
    __tm_prefix__: ClassVar[str]
    __tm_cs__: ClassVar[str]  # the control sequence, once registered (not for a colour); see `control_name`

    @classmethod
    def declared_default(cls) -> T | None:
        """The class's `default` (None when it has none): reading `default` through a class is ambiguous to a type
        checker, this is not."""
        return getattr(cls, "default", None)

    def __init__(self, value: T) -> None:
        """A document's setting for this value (D1a): `FactGap(Length("3mm"))`, checked against the declared type."""
        if not isinstance(value, kind := type(self).__tm_kind__.python):
            raise DeclarationError(f"{type(self).__name__}({value!r}): expected a {kind}", code="TM-M014")
        if why := plates_outside(type(self).plates, value):
            raise DeclarationError(f"{type(self).__name__}: {value!r} {why}", code="TM-M070")
        self.value = value

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.value!r})"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        doc = document_of(cls)
        arg = next(
            (typing.get_args(b)[0] for b in cls.__dict__.get("__orig_bases__", ()) if typing.get_origin(b) is Value),
            None,
        )
        marks = typing.get_args(arg)[1:] if typing.get_origin(arg) is typing.Annotated else ()
        kind = next((m for m in marks if isinstance(m, ValueKind)), TEXT_KIND if TEXT in marks else _KINDS.get(arg))
        if kind is None:
            raise DeclarationError(
                f"{cls.__qualname__}: base must be Value of Length, Colour, Bool, Text or Raw, or of a package's own "
                f"kind (etoolbox's Toggle), not {arg!r}",
                code="TM-M012",
                path=cls.__name__,
            )
        defined = cls.defined_by is not None
        if "default" not in cls.__dict__ and not kind.may_omit and not defined:
            raise DeclarationError(f"{cls.__qualname__}: no default", code="TM-M013", path=cls.__name__)
        if defined and "default" in cls.__dict__:
            raise DeclarationError(
                f"{cls.__qualname__}: has a default, but a library block defines it",
                code="TM-M032",
                path=cls.__name__,
                hint="remove the default: the block is the definition",
            )
        if "cs" in cls.__dict__:
            if kind.named:
                raise DeclarationError(
                    f"{cls.__qualname__}: a colour is named with colour_name, not cs", code="TM-M012", path=cls.__name__
                )
            Cs(cls.__dict__["cs"], Syntax.LATEX2E)  # a control word (TM-M027)
        if cls.colour_name is not None and not kind.named:
            raise DeclarationError(
                f"{cls.__qualname__}: colour_name belongs to a Value[Colour]", code="TM-M012", path=cls.__name__
            )
        default = cls.__dict__.get("default")
        if default is not None and not isinstance(default, kind.python):
            raise DeclarationError(
                f"{cls.__qualname__}: default {default!r} is not a {kind.name}", code="TM-M014", path=cls.__name__
            )
        _check_plates(cls, kind, default)
        cls.__tm_doc__, cls.__tm_kind__ = doc, kind
        cls.needs_packages = tuple(
            sorted({*cls.needs_packages, *kind.needs}, key=lambda p: p if isinstance(p, str) else p.name)
        )


type AnyValue = Value[Any]  # the kind, not the type, decides what `T` may be: a package adds its own (`Dual`)
