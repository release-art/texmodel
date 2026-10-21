"""The single error hierarchy (E1): every error carries a stable code, a path into the Doc and a fix hint."""


class TexmodelError(Exception):
    """Base of every error texmodel raises."""

    def __init__(self, message: str, *, code: str = "TM-E000", path: str = "", hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.hint = hint


class DeclarationError(TexmodelError):
    """A component, package or `[tool.texmodel]` declaration is invalid."""


class ValidationError(TexmodelError):
    """A Doc or spec breaks a rule."""


class CompileError(TexmodelError):
    """A compile failed (raised by `CompileResult.raise_for_status`)."""


class VerifyError(TexmodelError):
    """A PDF verification failed."""


class MigrationError(TexmodelError):
    """A spec cannot be migrated to the current schema."""


class ToolchainError(TexmodelError):
    """A required external tool is missing or unusable."""
