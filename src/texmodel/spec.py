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

A `Document` is data too, read with the package its names belong to (`from_dict(package, data)`): its `content` is a
list of nodes, its `options` a list of strings, its `settings` a list of `{"type": "FactGap", "value": "3mm"}` and its
`preamble` a mapping of slot to a list of TeX strings and entries (`{"type": "PdfInfo", "entries": {...}}`).
"""

import typing
from collections.abc import Iterable, Mapping, Sequence
from typing import Annotated, Any, Literal

import pydantic
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode

from ._internal.preamble_data import PreambleData, preamble_data
from ._internal.values import plates_outside
from .body import Comment
from .components import AnyValue, Children, Command, Environment, Node, Value, concrete_kinds
from .document import OPTION, Document
from .errors import DeclarationError, Violation
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


def _document_path(loc: Sequence[str | int]) -> str:
    """Where `violations()` and the plan name a part of a document: `settings[0].value`, `preamble.after_package[1]`,
    `Card[0]/Name[1].text`. The tag that tells the members of a union apart is not part of a path."""
    if loc[0] == "content":
        return _path(f"{loc[2]}[{loc[1]}]", loc[3:]) if len(loc) > 3 else f"content[{loc[1]}]"
    path, tag = str(loc[0]), False
    for part in loc[1:]:
        if isinstance(part, int):
            path, tag = f"{path}[{part}]", True
        elif tag:
            tag = False
        else:
            path += f".{part}"
    return path


def _values(package: Package) -> dict[str, type[AnyValue]]:
    return {c.__name__: typing.cast("type[AnyValue]", c) for c in package.visible if issubclass(c, Value)}


def _setting_type(cls: type[AnyValue]) -> Any:  # noqa: ANN401
    """What a setting's `value` is in data: the kind's type, and for a colour with `plates`, inside them."""

    def inside(value: Any) -> Any:  # noqa: ANN401
        if why := plates_outside(cls.plates, value):
            raise ValueError(why)
        return value

    return Annotated[cls.__tm_kind__.python, pydantic.AfterValidator(inside)]


def _document_model(package: Package) -> type[pydantic.BaseModel]:
    """The data of a `Document` of this package as a model: the nodes and values it registers are what data may name."""
    fields: dict[str, Any] = {
        "type": (Literal["Document"], "Document"),
        "options": (tuple[Annotated[str, pydantic.Field(pattern=f"^{OPTION.pattern}$")], ...], ()),
        "preamble": (PreambleData, PreambleData()),
        "content": (tuple[Annotated[Node, Children(package)], ...], ()),
    }
    if values := _values(package):
        settings: list[Any] = [
            pydantic.create_model(
                f"{name}Setting",
                type=typing.cast("Any", (Literal[name], ...)),
                value=typing.cast("Any", (_setting_type(cls), ...)),
            )
            for name, cls in values.items()
        ]
        union = typing.Union[tuple(settings)]  # noqa: UP007  # a union of as many models as the package has values
        fields["settings"] = (tuple[Annotated[union, pydantic.Field(discriminator="type")], ...], ())
    return pydantic.create_model("Document", __config__=pydantic.ConfigDict(extra="forbid"), **fields)


def _document_from(package: Package, data: Mapping[str, object]) -> Document:
    try:
        found: Any = _document_model(package).model_validate(data)
    except DeclarationError as exc:  # a colour component outside [0, 1] stops the validation
        raise ExceptionGroup("invalid Document", [Violation("TM-C020", "settings", str(exc)).error()]) from exc
    except pydantic.ValidationError as exc:
        raise ExceptionGroup(
            "invalid Document",
            [Violation("TM-C020", _document_path(e["loc"]), e["msg"]).error() for e in exc.errors(include_url=False)],
        ) from exc
    values = _values(package)
    return Document(
        *found.content,
        options=found.options,
        settings=[values[s.type](s.value) for s in getattr(found, "settings", ())],
        preamble=found.preamble.slots(),
    )


@typing.overload
def from_dict(target: type[Command] | type[Environment], data: Mapping[str, object]) -> Node: ...
@typing.overload
def from_dict(target: Package, data: Mapping[str, object]) -> Document: ...
def from_dict(target: type[Command] | type[Environment] | Package, data: Mapping[str, object]) -> Node | Document:
    """The node `data` describes, as an instance of `target`; given a `Package`, the `Document` of that package. Raises
    an `ExceptionGroup` of `ValidationError` (E2)."""
    if isinstance(target, Package):
        return _document_from(target, data)
    cls = target
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


def _setting_data(setting: AnyValue) -> dict[str, object]:
    python: Any = type(setting).__tm_kind__.python
    return {
        "type": type(setting).__name__,
        "value": pydantic.TypeAdapter[object](python).dump_python(setting.value, mode="json"),
    }


def to_dict(node: Node | Document) -> dict[str, object]:
    """The data of `node`, in the shape `from_dict` reads: the fields it was given (`model_fields_set`), as given. A
    `Document` writes what it holds: options, settings and preamble slots when there are any, and its content."""
    if isinstance(node, Document):
        out: dict[str, object] = {"type": "Document"}
        if node.options:
            out["options"] = list(node.options)
        if node.settings:
            out["settings"] = [_setting_data(v) for v in node.settings]
        if preamble := preamble_data(node.preamble):
            out["preamble"] = preamble
        return out | {"content": [to_dict(child) for child in node.content]}
    out = {"type": type(node).__name__}
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
            todo += [k for t in getattr(cls, "__tm_grammar__", ()) for k in concrete_kinds(t.kind)]
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
    nodes = [c for c in package.visible if issubclass(c, Command | Environment)]
    inputs: list[tuple[str, JsonSchemaMode, Any]] = [
        (c.__name__, "validation", pydantic.TypeAdapter(c).core_schema) for c in nodes
    ]
    inputs.append(("Document", "validation", pydantic.TypeAdapter(_document_model(package)).core_schema))
    _, defs = GenerateJsonSchema(ref_template="#/$defs/{model}").generate_definitions(inputs)
    schema: dict[str, Any] = {"$defs": defs}
    schema |= {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": package.name,
        "$ref": "#/$defs/Document",
    }
    for cls in package.visible:
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
