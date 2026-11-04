"""The data of a component, as pydantic reads it: a model generated from the class's arguments, and the schema of a
list of children. A node is a plain dataclass; `texmodel.spec` is what users call."""

import dataclasses
import functools
import typing
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

import pydantic
from pydantic_core import CoreSchema, core_schema

from ..body import Comment
from ..components import Command, Environment, Node, Passthrough, concrete_kinds

if TYPE_CHECKING:
    from ..package import Package


type Component = type[Command] | type[Environment] | type[Passthrough]


def _tag(value: object) -> object:
    """A child's component in data (`"type"`), or the class name of a node given as it is."""
    return value.get("type") if isinstance(value, Mapping) else type(value).__name__  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]


_COMMENT_MODELS: dict[type[Comment], type[pydantic.BaseModel]] = {}


def _comment_model(kind: type[Comment]) -> type[pydantic.BaseModel]:
    """A comment's fields as a model, for data and the schema (a `Comment` is not a pydantic model)."""
    if kind not in _COMMENT_MODELS:
        fields: dict[str, Any] = dict.fromkeys(kind.__tm_fields__, (str, ...))
        _COMMENT_MODELS[kind] = pydantic.create_model(kind.__name__, __doc__=kind.__doc__, **fields)
    return _COMMENT_MODELS[kind]


class _Data(pydantic.BaseModel):
    """What the data model of every component shares: its fields may be named by an old name (`field(renamed_from=)`);
    both names given is an error."""

    model_config = pydantic.ConfigDict(defer_build=True, protected_namespaces=())
    __old__: ClassVar[Mapping[str, str]] = {}

    @pydantic.model_validator(mode="before")
    @classmethod
    def _renamed(cls, data: object) -> object:
        if not cls.__old__ or not isinstance(data, Mapping):
            return data
        out = dict(typing.cast("Mapping[str, object]", data))
        for was, name in cls.__old__.items():
            if was in out:
                if name in out:
                    raise ValueError(f"{name!r} and its old name {was!r} are both given")
                out[name] = out.pop(was)
        return out


@functools.cache
def data_model(cls: Component) -> type[pydantic.BaseModel]:
    """The data of a component as a model: its arguments, and for an environment its children. Built on first use."""
    args = {a.name: a for a in cls.__tm_args__}
    old = {a.renamed_from: a.name for a in cls.__tm_args__ if a.renamed_from}
    fields: dict[str, Any] = {}
    for f in cls.__tm_fields__:
        if f.name == "content":
            fields["content"] = (tuple[Annotated[Node, Children(typing.cast("type[Environment]", cls))], ...], ...)
            continue
        a = args[f.name]
        extra: dict[str, Any] = {f"x-{k}": v for k, v in a.meta.items()}
        if a.renamed_from is not None:
            extra = {"x-renamed-from": a.renamed_from, **extra}
        fields[a.name] = (
            a.hint,
            pydantic.Field(a.default if a.optional else ..., description=a.doc, json_schema_extra=extra or None),
        )

    model = pydantic.create_model(
        cls.__name__,
        __base__=_Data,
        __doc__=cls.__doc__,
        **fields,
    )
    model.__old__ = old
    return model


def _built(cls: Component) -> Callable[[pydantic.BaseModel], Node]:
    """What turns a component's data model, once validated, into the node: the fields the data gave are the node's."""

    def build(model: pydantic.BaseModel) -> Node:
        given = {k: getattr(model, k) for k in model.model_fields_set}
        children = given.pop("content", ())
        return cls(*children, **given) if issubclass(cls, Environment) else cls(**given)  # pyright: ignore[reportArgumentType]

    return build


def validated(cls: Component, data: Mapping[str, object]) -> Node:
    """The node `data` describes; raises `pydantic.ValidationError`."""
    return _built(cls)(data_model(cls).model_validate(data))


@dataclasses.dataclass(frozen=True)
class Children:
    """The schema of a list of nodes in data: a union, told apart by `"type"`, of the components an environment's
    grammar names, or (given a package) of every command and environment it registers and `Passthrough`; and `Comment`
    and the package's comment classes."""

    owner: "type[Environment] | Package"

    def __get_pydantic_core_schema__(self, source: object, handler: pydantic.GetCoreSchemaHandler) -> CoreSchema:
        if isinstance(self.owner, type):
            package = typing.cast("Package | None", getattr(self.owner, "__tm_package__", None))
            kinds = [k for t in self.owner.__tm_grammar__ for k in concrete_kinds(t.kind)]
        else:
            package = self.owner
            kinds = [c for c in package.visible if issubclass(c, Command | Environment)] + [Passthrough]
        choices: dict[Any, CoreSchema] = {
            kind.__name__: core_schema.no_info_after_validator_function(
                _built(kind), handler.generate_schema(data_model(kind))
            )
            for kind in kinds
        }
        for kind in (Comment, *(package.comments if package else ())):
            choices[kind.__name__] = core_schema.no_info_after_validator_function(
                lambda model, kind=kind: kind(**dict(model)),
                handler.generate_schema(_comment_model(kind)),
            )
        return core_schema.tagged_union_schema(choices, discriminator=_tag)
