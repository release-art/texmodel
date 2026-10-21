"""Components (M1): a `Command` is declared as a class; its fields are its arguments, its docstring its documentation.

```python
pkg = Package("acme-cards", prefix="ac")

@pkg.command
class Slot(Command):
    '''A labelled paragraph; the label prints as its heading.'''
    text: Text
    label: Text | None = None      # optional: keyword-only, rendered as TeX's one optional argument
```

The body is TeX in `slot.tex` beside the class, or a short inline `body=`: `class Slot(Command, body="...")`.
Inside it `#text` is the argument named `text`. A bad declaration is refused when the class is defined.
"""

import dataclasses
import inspect
import re
import sys
import types
import typing
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar, dataclass_transform

from ._internal.render import Arg, Spec, check_name
from .errors import DeclarationError
from .types import TEXT


@dataclass_transform(frozen_default=True)
class Command:
    """A TeX command (`\\newcommand`) whose arguments are the class's fields."""

    __tm_inline__: ClassVar[str | None]
    __tm_unused__: ClassVar[tuple[str, ...]]
    __tm_args__: ClassVar[tuple[Arg, ...]]
    __tm_doc__: ClassVar[str]

    def __init_subclass__(cls, *, body: str | None = None, unused: Sequence[str] = (), **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        check_name(cls.__name__, "component")
        doc = (cls.__dict__.get("__doc__") or "").strip()
        if not doc:
            raise DeclarationError(f"{cls.__qualname__}: document the component in its docstring", code="TM-M002")
        cls.__tm_inline__, cls.__tm_unused__, cls.__tm_doc__ = body, tuple(unused), doc
        # Optional fields are keyword-only (M2): mark them before the dataclass is built.
        for name in inspect.get_annotations(cls):
            if name in cls.__dict__ and not name.startswith("__"):
                setattr(cls, name, dataclasses.field(default=cls.__dict__[name], kw_only=True))
        dataclasses.dataclass(frozen=True)(cls)
        cls.__doc__ = doc
        cls.__tm_args__ = _arguments(cls)


def _arguments(cls: type[Command]) -> tuple[Arg, ...]:
    hints = typing.get_type_hints(cls, include_extras=True)
    args: list[Arg] = []
    for f in dataclasses.fields(cls):  # pyright: ignore[reportArgumentType]
        if not _is_text(hints[f.name]):
            raise DeclarationError(
                f"{cls.__qualname__}.{f.name}: unsupported type {hints[f.name]!r}; use Text or Text | None",
                code="TM-M004",
                path=f"{cls.__name__}.{f.name}",
            )
        args.append(Arg(f.name, optional=f.default is not dataclasses.MISSING))
    if sum(a.optional for a in args) > 1:
        raise DeclarationError(
            f"{cls.__qualname__}: more than one optional argument (TeX's \\newcommand allows one)",
            code="TM-M003",
            path=cls.__name__,
        )
    return tuple(args)


def _is_text(hint: Any) -> bool:
    """`Text`, or `Text | None`."""
    members = typing.get_args(hint) if isinstance(hint, types.UnionType) else (hint,)
    return all(
        m is type(None) or (typing.get_origin(m) is typing.Annotated and TEXT in typing.get_args(m)[1:])
        for m in members
    )


def snake(name: str) -> str:
    """`FactGap` -> `fact_gap`."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def spec_of(cls: type[Command]) -> Spec:
    """The declaration as the renderer sees it, with the body found (inline, or `<snake_name>.tex` beside the class)."""
    here = Path(sys.modules[cls.__module__].__file__ or ".").parent
    candidate = here / f"{snake(cls.__name__)}.tex"
    qualname = f"{cls.__module__}.{cls.__qualname__}"
    if cls.__tm_inline__ is not None and candidate.is_file():
        raise DeclarationError(
            f"{qualname}: has both an inline body and {candidate.name}; keep one", code="TM-M005", path=cls.__name__
        )
    if cls.__tm_inline__ is not None:
        body, origin = cls.__tm_inline__, "inline"
    elif candidate.is_file():
        body, origin = candidate.read_text(encoding="utf-8"), candidate.name
    else:
        raise DeclarationError(
            f"{qualname}: no body; write {candidate} or pass body='...'", code="TM-M006", path=cls.__name__
        )
    return Spec(cls.__name__, cls.__tm_doc__, cls.__tm_args__, body, origin, qualname, cls.__tm_unused__)
