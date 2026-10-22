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
from collections.abc import Mapping, Sequence
from typing import Annotated, Any

import pydantic

from .body import Comment
from .components import Command, Environment, Node
from .errors import ValidationError, Violation
from .types import Choice, Raw

_MODELS: dict[tuple[type[Environment], tuple[type[Comment], ...]], type[pydantic.BaseModel]] = {}
_COMMENT_MODELS: dict[type[Comment], type[pydantic.BaseModel]] = {}


def _tag(value: object) -> object:
    return value.get("type") if isinstance(value, Mapping) else type(value).__name__  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]


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
        members: list[Any] = []
        for t in cls.__tm_grammar__:
            kind = t.kind
            members.append(
                kind if issubclass(kind, Command) else _model(typing.cast(type[Environment], kind), comments)
            )
        members += map(_comment_model, (Comment, *comments))
        tagged = tuple(Annotated[m, pydantic.Tag(m.__name__)] for m in members)
        fields: dict[str, Any] = {"content": (list[Annotated[typing.Union[tagged], pydantic.Discriminator(_tag)]], ...)}  # noqa: UP007
        for a in cls.__tm_args__:
            kind = a.choice or (Raw if a.raw else str)
            fields[a.name] = (kind | None, None) if a.optional else (kind, ...)
        _MODELS[cls, comments] = pydantic.create_model(cls.__name__, **fields)
        _MODELS[cls, comments].__tm_cls__ = cls  # pyright: ignore[reportAttributeAccessIssue]
    return _MODELS[cls, comments]


def _node(value: Any) -> Node:  # noqa: ANN401  # an instance of a model built at run time, or a Command
    if isinstance(value, Command):
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


def json_schema(cls: type[Command] | type[Environment], *, comments: Sequence[type[Comment]] = ()) -> dict[str, Any]:
    """JSON Schema of the data `from_dict(cls, ..., comments=)` accepts; docstrings are descriptions."""
    if issubclass(cls, Command):
        return pydantic.TypeAdapter(cls).json_schema()
    return _model(cls, tuple(comments)).model_json_schema()


__all__ = ["ValidationError", "from_dict", "json_schema", "to_dict"]
