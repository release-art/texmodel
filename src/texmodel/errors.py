"""The error hierarchy (E1): every error carries a stable code, a path into the Doc and a fix hint."""

import dataclasses


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


__all__ = ["DeclarationError", "MigrationError", "TexmodelError", "ValidationError", "Violation"]
