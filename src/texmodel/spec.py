"""A Doc from plain data and back (D2, S): `from_dict`, `to_dict` and `json_schema`, built on pydantic.

Data is what TOML or JSON gives: a component is a dict with its fields, an environment also has `content`, a list of
children, and a child names its component with `"type"`:

```python
from_dict(Card, {"content": [
    {"type": "CardFront", "content": [{"type": "CardImage", "path": "a.jpg"}]},
    {"type": "CardBack", "content": [{"type": "Name", "text": "Fox"}, {"type": "LeadFact", "text": "..."}]},
]})
```

Fields are coerced as pydantic does by default (a `Raw` field takes a string). Everything wrong is reported at once,
as an `ExceptionGroup` of `ValidationError`, each with the path `validate()` would give it; the grammar (counts and
order, M4) is checked by `validate()` on the result, so a document that loads is not yet a valid one.
"""

import typing
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Annotated, Any

import pydantic
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode

from .body import Comment
from .components import Command, Environment, Node, Passthrough, Value
from .errors import ValidationError, Violation
from .package import Package
from .types import Choice, Raw

_MODELS: dict[tuple[type[Environment], tuple[type[Comment], ...]], type[pydantic.BaseModel]] = {}
_COMMENT_MODELS: dict[type[Comment], type[pydantic.BaseModel]] = {}


def _tag(value: object) -> object:
    return value.get("type") if isinstance(value, Mapping) else type(value).__name__  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]


def _renamer(cls: type[Command] | type[Environment] | type[Passthrough]) -> Callable[[object], object]:
    """A before-validator that moves a field's old key (`field(renamed_from=)`) to its name; both given is an error."""
    old = {a.renamed_from: a.name for a in cls.__tm_args__ if a.renamed_from}

    def rename(data: object) -> object:
        if not old or not isinstance(data, Mapping):
            return data
        out = dict(typing.cast("Mapping[str, object]", data))
        for was, name in old.items():
            if was in out:
                if name in out:
                    raise ValueError(f"{name!r} and its old name {was!r} are both given")
                out[name] = out.pop(was)
        return out

    return rename


def _same(data: object) -> object:
    return data


def _comment_model(kind: type[Comment]) -> type[pydantic.BaseModel]:
    if kind not in _COMMENT_MODELS:
        fields: dict[str, Any] = dict.fromkeys(kind.__tm_fields__, (str, ...))
        _COMMENT_MODELS[kind] = pydantic.create_model(kind.__name__, __doc__=kind.__doc__, **fields)
        _COMMENT_MODELS[kind].__tm_cls__ = kind  # pyright: ignore[reportAttributeAccessIssue]
    return _COMMENT_MODELS[kind]


def _model(cls: type[Environment], comments: tuple[type[Comment], ...]) -> type[pydantic.BaseModel]:
    """The pydantic model of an environment: `content` limited to its grammar's components and to `Comment` and
    `comments` (a comment is not in a grammar), and its arguments."""
    if (cls, comments) not in _MODELS:
        members: list[tuple[Any, Callable[[object], object]]] = []
        for t in cls.__tm_grammar__:
            kind = typing.cast("type[Command] | type[Environment] | type[Passthrough]", t.kind)
            members.append((_model(kind, comments) if issubclass(kind, Environment) else kind, _renamer(kind)))
        members += [(_comment_model(c), _same) for c in (Comment, *comments)]
        tagged = tuple(Annotated[m, pydantic.BeforeValidator(r), pydantic.Tag(m.__name__)] for m, r in members)
        fields: dict[str, Any] = {"content": (list[Annotated[typing.Union[tagged], pydantic.Discriminator(_tag)]], ...)}  # noqa: UP007
        for a in cls.__tm_args__:
            kind = a.choice or (Raw if a.raw else str)
            fields[a.name] = (kind | None, None) if a.optional else (kind, ...)
        _MODELS[cls, comments] = pydantic.create_model(cls.__name__, **fields)
        _MODELS[cls, comments].__tm_cls__ = cls  # pyright: ignore[reportAttributeAccessIssue]
    return _MODELS[cls, comments]


def _node(value: Any) -> Node:  # noqa: ANN401  # an instance of a model built at run time, or a Command
    if isinstance(value, Command | Passthrough):
        return value
    cls: type[Environment] | type[Comment] = value.__tm_cls__
    if issubclass(cls, Comment):
        return cls(**{f: getattr(value, f) for f in cls.__tm_fields__})
    args = {a.name: getattr(value, a.name) for a in cls.__tm_args__}
    return cls(*(_node(c) for c in value.content), **args)


def _path(root: str, loc: Sequence[str | int]) -> str:
    """`('content', 1, 'LeadFact', 'text')` under `Card` is `Card/LeadFact[1].text`, as `validate()` writes it."""
    path, index = root, None
    for part in loc:
        if part == "content":
            continue
        if isinstance(part, int):
            index = part
        elif index is not None:
            path, index = f"{path}/{part}[{index}]", None
        else:
            path = f"{path}.{part}"
    return path if index is None else f"{path}/content[{index}]"  # a child no component of the grammar fits


def from_dict(
    cls: type[Command] | type[Environment], data: Mapping[str, object], *, comments: Sequence[type[Comment]] = ()
) -> Node:
    """The node `data` describes, as an instance of `cls`; raises an `ExceptionGroup` of `ValidationError` (E2).
    A child may also be a `Comment` (`"type": "Comment"`, `"text"`) or an instance of one of `comments`."""
    try:
        data = typing.cast("Mapping[str, object]", _renamer(cls)(data))
    except ValueError as exc:  # a renamed key given with its new name too
        raise ExceptionGroup(f"invalid {cls.__name__}", [Violation("TM-C020", cls.__name__, str(exc)).error()]) from exc
    try:
        if issubclass(cls, Command):
            return pydantic.TypeAdapter(cls).validate_python(data)  # pyright: ignore[reportUnknownVariableType]
        return _node(_model(cls, tuple(comments)).model_validate(data))
    except pydantic.ValidationError as exc:
        raise ExceptionGroup(
            f"invalid {cls.__name__}",
            [
                Violation("TM-C020", _path(cls.__name__, e["loc"]), e["msg"]).error()
                for e in exc.errors(include_url=False)
            ],
        ) from exc


def to_dict(node: Node) -> dict[str, object]:
    """The data of `node`, in the shape `from_dict` reads; an optional field that is `None` is left out."""
    out: dict[str, object] = {"type": type(node).__name__}
    if isinstance(node, Comment):
        return out | {f: getattr(node, f) for f in node.__tm_fields__}
    for a in type(node).__tm_args__:
        value = getattr(node, a.name)
        if value is not None:
            out[a.name] = value.tex if isinstance(value, Raw) else value.name if isinstance(value, Choice) else value
    if isinstance(node, Environment):
        out["content"] = [to_dict(child) for child in node.content]
    return out


def _reachable(classes: Iterable[type]) -> dict[str, type]:
    """The given classes and every component their grammars name, by class name."""
    found: dict[str, type] = {}
    todo = list(classes)
    while todo:
        cls = todo.pop()
        if cls.__name__ not in found:
            found[cls.__name__] = cls
            todo += [t.kind for t in getattr(cls, "__tm_grammar__", ())]
    return found


def _requires_type(node: object) -> None:
    """A child is one of several components, told apart by `"type"`: each branch of such a union requires it, so a
    child's data matches exactly one branch."""
    if isinstance(node, dict):
        branches = typing.cast("dict[str, Any]", node).get("oneOf")
        if isinstance(branches, list) and all("$ref" in b for b in typing.cast("list[dict[str, Any]]", branches)):
            for branch in typing.cast("list[dict[str, Any]]", branches):
                branch["required"] = ["type"]
        for value in typing.cast("dict[str, Any]", node).values():
            _requires_type(value)
    elif isinstance(node, list):
        for value in typing.cast("list[object]", node):
            _requires_type(value)


def _annotate(schema: dict[str, Any], classes: Iterable[type], comments: Iterable[type] = ()) -> None:
    """Name every component by its `"type"` constant, and record `x-renamed-from` on each renamed field (§21a 15)."""
    named = _reachable(classes)
    kinds = {*named, *(c.__name__ for c in (Comment, *comments))}
    for node in (schema, *schema.get("$defs", {}).values()):
        title = str(node.get("title"))
        if title in kinds:
            node.setdefault("properties", {})["type"] = {"const": title}
        for a in getattr(named.get(title), "__tm_args__", ()):
            if a.renamed_from and a.name in node.get("properties", {}):
                node["properties"][a.name]["x-renamed-from"] = a.renamed_from
    _requires_type(schema)


_VALUE_TYPES = {"Length": "string", "Colour": "string", "Bool": "boolean", "Text": "string", "Raw": "string"}


def _package_schema(package: Package, comments: tuple[type[Comment], ...]) -> dict[str, Any]:
    """One schema for a package: a `$defs` entry per command and environment, and `Value.<Name>` per value."""
    nodes = [c for c in package.registered if issubclass(c, Command | Environment)]
    inputs: list[tuple[str, JsonSchemaMode, Any]] = [
        (
            c.__name__,
            "validation",
            pydantic.TypeAdapter(c if issubclass(c, Command) else _model(c, comments)).core_schema,
        )
        for c in nodes
    ]
    _, defs = GenerateJsonSchema(ref_template="#/$defs/{model}").generate_definitions(inputs)
    schema: dict[str, Any] = {"$defs": defs}
    schema |= {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": package.name}
    for cls in package.registered:
        if issubclass(cls, Value):
            schema["$defs"][f"Value.{cls.__name__}"] = {
                "title": cls.__name__,
                "description": cls.__tm_doc__,
                "type": _VALUE_TYPES[cls.__tm_kind__],
            }
    _annotate(schema, nodes, comments)
    return schema


def json_schema(
    target: type[Command] | type[Environment] | Package, *, comments: Sequence[type[Comment]] = ()
) -> dict[str, Any]:
    """JSON Schema of the data `from_dict(cls, ..., comments=)` accepts; docstrings are descriptions. Given a `Package`,
    one schema with a `$defs` entry for every registered component and value; a renamed field has `x-renamed-from`."""
    if isinstance(target, Package):
        return _package_schema(target, tuple(comments))
    schema = (
        pydantic.TypeAdapter(target).json_schema()
        if issubclass(target, Command)
        else _model(target, tuple(comments)).model_json_schema()
    )
    _annotate(schema, [target], comments)
    return schema


__all__ = ["ValidationError", "from_dict", "json_schema", "to_dict"]
