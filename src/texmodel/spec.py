"""A Doc from plain data and back (D2, S): `from_dict`, `to_dict` and `json_schema`, built on pydantic.

Data is what TOML or JSON gives: a component is a dict with its fields, an environment also has `content`, a list of
children, and a child names its component with `"type"`:

```python
from_dict(Card, {"content": [
    {"type": "CardFront", "content": [{"type": "CardImage", "path": "a.jpg"}]},
    {"type": "CardBack", "content": [{"type": "Name", "text": "Fox"}, {"type": "LeadFact", "text": "..."}]},
]})
```

Fields are coerced as pydantic does by default (a `Raw` field takes a string). A child may be a comment: `Comment`, or
one of the classes the environment's package lists in `Package(comments=)`. Everything wrong is reported at once, as an
`ExceptionGroup` of `ValidationError`, each with the path `violations()` would give it; the grammar (counts and order,
M4) is checked by `violations()` on the result, so a document that loads is not yet a valid one.

A node from data knows which fields the data gave (`model_fields_set`), and `to_dict` writes those, so a round trip
keeps them.
"""

import typing
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pydantic
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode

from .body import Comment
from .components import Command, Environment, Node, Value
from .errors import Violation
from .package import Package


def _path(root: str, loc: Sequence[str | int]) -> str:
    """`('content', 1, 'LeadFact', 'text')` under `Card` is `Card/LeadFact[1].text`, as `violations()` writes it."""
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


def from_dict(cls: type[Command] | type[Environment], data: Mapping[str, object]) -> Node:
    """The node `data` describes, as an instance of `cls`; raises an `ExceptionGroup` of `ValidationError` (E2)."""
    try:
        return cls.model_validate(data)
    except pydantic.ValidationError as exc:
        raise ExceptionGroup(
            f"invalid {cls.__name__}",
            [
                Violation("TM-C020", _path(cls.__name__, e["loc"]), e["msg"]).error()
                for e in exc.errors(include_url=False)
            ],
        ) from exc


def to_dict(node: Node) -> dict[str, object]:
    """The data of `node`, in the shape `from_dict` reads: the fields it was given (`model_fields_set`), as given."""
    out: dict[str, object] = {"type": type(node).__name__}
    if isinstance(node, Comment):
        return out | {f: getattr(node, f) for f in node.__tm_fields__}
    out |= node.model_dump(mode="json", exclude_unset=True, exclude={"content"})
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


def _x_keys(meta: Mapping[str, object]) -> dict[str, object]:
    """`{"audience": "deck"}` as `{"x-audience": "deck"}`."""
    return {f"x-{k}": v for k, v in meta.items()}


def _comments(classes: Iterable[type]) -> set[str]:
    """`Comment` and the comment classes of the packages these classes are registered with."""
    packages = (getattr(cls, "__tm_package__", None) for cls in classes)
    return {"Comment", *(c.__name__ for p in packages if isinstance(p, Package) for c in p.comments)}


def _annotate(schema: dict[str, Any], classes: Iterable[type]) -> None:
    """Name every component and comment by its `"type"` constant and add the `meta` of components (`x-` keys); a
    field's doc, old name and meta are in its schema already (`field()`, `arg()`)."""
    named = _reachable(classes)
    kinds = {*named, *_comments(named.values())}
    for node in (schema, *schema.get("$defs", {}).values()):
        title = str(node.get("title"))
        if title in kinds:
            node.setdefault("properties", {})["type"] = {"const": title}
        node |= _x_keys(getattr(named.get(title), "meta", {}))
    _requires_type(schema)


def _package_schema(package: Package) -> dict[str, Any]:
    """One schema for a package: a `$defs` entry per command and environment, and `Value.<Name>` per value."""
    nodes = [c for c in package.registered if issubclass(c, Command | Environment)]
    inputs: list[tuple[str, JsonSchemaMode, Any]] = [
        (c.__name__, "validation", pydantic.TypeAdapter(c).core_schema) for c in nodes
    ]
    _, defs = GenerateJsonSchema(ref_template="#/$defs/{model}").generate_definitions(inputs)
    schema: dict[str, Any] = {"$defs": defs}
    schema |= {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": package.name}
    for cls in package.registered:
        if issubclass(cls, Value):
            schema["$defs"][f"Value.{cls.__name__}"] = {
                "title": cls.__name__,
                "description": cls.__tm_doc__,
                "type": cls.__tm_kind__.json_type,
                **_x_keys(cls.meta),
            }
    _annotate(schema, nodes)
    return schema


def json_schema(target: type[Command] | type[Environment] | Package) -> dict[str, Any]:
    """JSON Schema of the data `from_dict(cls, ...)` accepts; docstrings are descriptions. Given a `Package`, one schema
    with a `$defs` entry for every registered component and value; a renamed field has `x-renamed-from`."""
    if isinstance(target, Package):
        return _package_schema(target)
    schema = target.model_json_schema()
    _annotate(schema, [target])
    return schema


__all__ = ["from_dict", "json_schema", "to_dict"]
