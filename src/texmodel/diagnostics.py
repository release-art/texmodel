"""Typed compile diagnostics (C2): what a TeX log says, as data with stable codes (D5)."""

import dataclasses
import enum
from typing import Any, cast


class Severity(enum.StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclasses.dataclass(frozen=True, kw_only=True)
class Diagnostic:
    """One finding. `file`/`line` are the raw TeX location (mapped back to the Doc by C11 later)."""

    code: str = "TM-X000"
    severity: Severity = Severity.ERROR
    message: str = ""
    file: str | None = None
    line: int | None = None
    count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"kind": type(self).__name__, **dataclasses.asdict(self)}


@dataclasses.dataclass(frozen=True, kw_only=True)
class UndefinedControlSequence(Diagnostic):
    code: str = "TM-X010"
    name: str = ""


@dataclasses.dataclass(frozen=True, kw_only=True)
class MissingCharacter(Diagnostic):
    """The font has no glyph for `codepoint`; an error by default, never a silent substitution."""

    code: str = "TM-X011"
    font: str = ""
    codepoint: int = 0


@dataclasses.dataclass(frozen=True, kw_only=True)
class OverfullBox(Diagnostic):
    code: str = "TM-X012"
    severity: Severity = Severity.WARNING
    amount_pt: float = 0.0
    direction: str = "h"  # "h" too wide, "v" too high


@dataclasses.dataclass(frozen=True, kw_only=True)
class MissingFile(Diagnostic):
    code: str = "TM-X013"
    name: str = ""


@dataclasses.dataclass(frozen=True, kw_only=True)
class PackageError(Diagnostic):
    code: str = "TM-X014"
    package: str = ""


@dataclasses.dataclass(frozen=True, kw_only=True)
class RerunNeeded(Diagnostic):
    code: str = "TM-X015"
    severity: Severity = Severity.WARNING


@dataclasses.dataclass(frozen=True, kw_only=True)
class UndefinedReference(Diagnostic):
    code: str = "TM-X018"
    severity: Severity = Severity.WARNING
    kind: str = "Reference"  # or "Citation"
    name: str = ""


@dataclasses.dataclass(frozen=True, kw_only=True)
class DocumentRefusal(Diagnostic):
    """A body refused to typeset (`texmodel:refuse:<reason>` in the log)."""

    code: str = "TM-X016"


@dataclasses.dataclass(frozen=True, kw_only=True)
class Measurement(Diagnostic):
    """A probe value (`texmodel:probe:<name>=<value>` in the log, C5a)."""

    code: str = "TM-X017"
    severity: Severity = Severity.INFO
    name: str = ""
    value: str = ""


@dataclasses.dataclass(frozen=True, kw_only=True)
class TexError(Diagnostic):
    """Any other TeX error, so an error the parser does not know is still reported (V5)."""

    code: str = "TM-X020"


@dataclasses.dataclass(frozen=True, kw_only=True)
class NotConverged(Diagnostic):
    """The pass limit was reached with the `.aux` still changing; `changed` names the entries (C1a)."""

    code: str = "TM-X030"
    changed: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True, kw_only=True)
class Unexplained(Diagnostic):
    """The compile failed (or timed out) and the log explains nothing."""

    code: str = "TM-X099"


KINDS: dict[str, type[Diagnostic]] = {
    cls.__name__: cls
    for cls in (
        Diagnostic,
        UndefinedControlSequence,
        MissingCharacter,
        OverfullBox,
        MissingFile,
        PackageError,
        RerunNeeded,
        UndefinedReference,
        DocumentRefusal,
        Measurement,
        TexError,
        NotConverged,
        Unexplained,
    )
}


def diagnostic_from_dict(data: dict[str, Any]) -> Diagnostic:
    fields: dict[str, Any] = {
        k: (tuple(cast("list[Any]", v)) if isinstance(v, list) else v) for k, v in data.items() if k != "kind"
    }
    fields["severity"] = Severity(fields["severity"])
    return KINDS[data["kind"]](**fields)
