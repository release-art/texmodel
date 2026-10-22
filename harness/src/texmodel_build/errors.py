"""Harness errors, in the same hierarchy as the core's (every one carries `.code`, `.path`, `.hint`)."""

from texmodel.errors import TexmodelError

from .diagnostics import Diagnostic


class CompileError(TexmodelError):
    """A compile failed (raised by `CompileResult.raise_for_status`); `diagnostics` carries every finding."""

    def __init__(self, message: str, *, diagnostics: tuple[Diagnostic, ...] = (), **kwargs: str) -> None:
        super().__init__(message, **kwargs)
        self.diagnostics = diagnostics


class ToolchainError(TexmodelError):
    """A required external tool or image is missing or unusable."""
