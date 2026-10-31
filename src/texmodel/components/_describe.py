"""A registered component as data."""

import dataclasses
import typing
from typing import TYPE_CHECKING, Literal

from .._internal.specs import env_spec_of, spec_of
from ..errors import DeclarationError
from ..types import ValueKind

if TYPE_CHECKING:
    pass

from ._node import Command, Environment
from ._values import Value


@dataclasses.dataclass(frozen=True)
class ArgumentInfo:
    """One argument of a registered command or environment."""

    name: str = dataclasses.field(metadata={"doc": "the field's name"})
    optional: bool = dataclasses.field(metadata={"doc": "it may be left out"})
    doc: str | None = dataclasses.field(metadata={"doc": "its `field(doc=)`, if it has one"})


@dataclasses.dataclass(frozen=True)
class Description:
    """What `describe` reports about a registered component or value."""

    category: Literal["command", "environment", "value"] = dataclasses.field(metadata={"doc": "what it is"})
    name: str = dataclasses.field(metadata={"doc": "the class name"})
    cs: str | None = dataclasses.field(
        metadata={"doc": "the control sequence without the backslash; None for a colour"}
    )
    doc: str = dataclasses.field(metadata={"doc": "the class's docstring"})
    arguments: tuple[ArgumentInfo, ...] = dataclasses.field(metadata={"doc": "in TeX order; empty for a value"})
    python: object | None = dataclasses.field(
        metadata={"doc": "a value's Python type (bool, Length, str, Raw, Colour); None otherwise"}
    )
    default: object | None = dataclasses.field(metadata={"doc": "a value's default; None otherwise"})
    colour_name: str | None = dataclasses.field(metadata={"doc": "a colour's name; None otherwise"})
    body: str | None = dataclasses.field(
        metadata={
            "doc": "a command's body or an environment's `begin`, with `#name` holes; None for a value or adopted"
        }
    )
    end: str | None = dataclasses.field(metadata={"doc": "an environment's `end`; None otherwise"})


def describe(cls: type) -> Description:
    """A registered command, environment or value class as data, so a program need not read its `__tm_*` attributes.
    An unregistered class is `TM-M019`."""
    if not hasattr(cls, "__tm_prefix__"):
        raise DeclarationError(
            f"{cls.__qualname__}: not registered with a package", code="TM-M019", hint="decorate it with @pkg.command"
        )
    if issubclass(cls, Value):
        kind: ValueKind = cls.__tm_kind__
        return Description(
            "value",
            cls.__name__,
            None if kind.named else cls.__tm_cs__,
            cls.__tm_doc__,
            (),
            kind.python,
            typing.cast("object | None", cls.declared_default()),
            cls.colour_name,
            None,
            None,
        )
    if not issubclass(cls, Command | Environment):
        raise DeclarationError(f"{cls.__qualname__}: not a command, environment or value", code="TM-M019")
    body = end = None
    if cls.defined_by is None and issubclass(cls, Command) and cls.__tm_inline__:
        body = spec_of(cls).body
    elif cls.defined_by is None and issubclass(cls, Environment) and cls.__tm_inline__[0]:
        spec = env_spec_of(cls)
        body, end = spec.begin, spec.end
    return Description(
        "command" if issubclass(cls, Command) else "environment",
        cls.__name__,
        cls.__tm_cs__,
        cls.__tm_doc__,
        tuple(ArgumentInfo(a.name, a.optional, a.doc) for a in cls.__tm_args__),
        None,
        None,
        None,
        body,
        end,
    )
