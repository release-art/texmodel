"""The error hierarchy (E1): every error carries a stable code, a path into the Doc and a fix hint."""

import dataclasses
from typing import Protocol


class TexmodelError(Exception):
    """Base of every error texmodel (and texmodel.run) raises."""

    def __init__(self, message: str, *, code: str = "TM-E000", path: str = "", hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.hint = hint


class DeclarationError(TexmodelError):
    """A component, package or `[tool.texmodel]` declaration is invalid."""


class ValidationError(TexmodelError):
    """A Doc or spec breaks a rule."""


class ValueRuleError(ValidationError, ValueError):
    """A value type refuses its own value when built. It is also a `ValueError`, so pydantic reports it with the field
    when the value is read from data."""


class MigrationError(TexmodelError):
    """A spec cannot be migrated to the current schema."""


@dataclasses.dataclass(frozen=True)
class Violation:
    """One broken rule in a Doc (D5, E2): `violations()` returns them all; raising APIs raise an `ExceptionGroup`."""

    code: str
    path: str
    message: str
    hint: str = ""

    def error(self) -> ValidationError:
        return ValidationError(self.message, code=self.code, path=self.path, hint=self.hint)


type _Colours = dict[str, frozenset[str] | None]


class _Coloured(Protocol):
    def colour_constraints(self) -> _Colours: ...


@dataclasses.dataclass(eq=False)
class CheckContext:
    """What one check of a tree reuses between its nodes: the colours each package allows, which cost a read of the
    package's LaTeX libraries. Make one for a check of many nodes (`node.violations(context)` for each of a document's
    nodes) and drop it after; the checks that are given none make their own. It is not shared between threads, and it
    does not see a package declared or changed after it first asked."""

    _colours: dict[_Coloured, _Colours] = dataclasses.field(default_factory=dict[_Coloured, _Colours], repr=False)

    def colours_of(self, package: _Coloured) -> _Colours:
        """`package.colour_constraints()`, worked out once for this context."""
        if package not in self._colours:
            self._colours[package] = package.colour_constraints()
        return self._colours[package]


__all__ = [
    "CheckContext",
    "DeclarationError",
    "MigrationError",
    "TexmodelError",
    "ValidationError",
    "ValueRuleError",
    "Violation",
]
