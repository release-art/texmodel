"""Typed compile diagnostics (C2): what a TeX log says, as data with stable codes (D5)."""

import dataclasses
import enum
import re
from fractions import Fraction
from typing import Any, cast

from texmodel.errors import DeclarationError
from texmodel.types import Length


@enum.unique
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
    path: str | None = None  # the component that wrote `line`, when the compile was given a Plan (C11)
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
class PackageWarning(Diagnostic):
    """A package's own warning, with its continuation lines joined: how a hand-written package reports a card that does
    not fit (`Card 'Moorhen' does not fit.`)."""

    code: str = "TM-X019"
    severity: Severity = Severity.WARNING
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
class Overset(Diagnostic):
    """`item` needs `needs_pt` and has `has_pt`: a card that does not fit, typed (B2). Read from a package warning by a
    `Measure` rule, or from a `texmodel:probe:fit.<item>=<needs>/<has>` line."""

    code: str = "TM-X031"
    item: str = ""
    needs_pt: float = 0.0
    has_pt: float = 0.0
    over_pt: float = 0.0


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
        PackageWarning,
        RerunNeeded,
        UndefinedReference,
        DocumentRefusal,
        Measurement,
        Overset,
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


@enum.unique
class MeasureKind(enum.Enum):
    FIT = "fit"  # the warning says an item needs more room than it has


@dataclasses.dataclass(frozen=True)
class Measure:
    """`[tool.texmodel.run.measures.<name>]`: how to read one package's warning as a typed measurement (B2).
    `pattern` is searched in the warning's message and has the named groups `item`, `needs` and `has`, lengths
    (`322.436pt`, `11mm`; a bare number is in pt)."""

    name: str
    package: str
    pattern: re.Pattern[str]
    kind: MeasureKind = MeasureKind.FIT

    @classmethod
    def declare(cls, name: str, package: str, pattern: str, kind: str = "fit") -> "Measure":
        """Refuses a rule that cannot work when the config is read (`TM-D032`), not when a log is."""
        try:
            compiled = re.compile(pattern)
            chosen = MeasureKind(kind)
        except (re.error, ValueError) as exc:
            raise DeclarationError(
                f"[tool.texmodel.run.measures.{name}]: {exc}", code="TM-D032", hint='kind is "fit"; pattern a regex'
            ) from exc
        if missing := {"item", "needs", "has"} - set(compiled.groupindex):
            raise DeclarationError(
                f"[tool.texmodel.run.measures.{name}]: pattern lacks the groups {sorted(missing)}",
                code="TM-D032",
                hint="use (?P<item>...), (?P<needs>...) and (?P<has>...)",
            )
        return cls(name, package, compiled, chosen)


def points(text: str) -> float:
    """A length in TeX points; a bare number is already in pt. Raises `DeclarationError` for anything else."""
    return float(Length(text if text.strip()[-1:].isalpha() else f"{text.strip()}pt").inches * Fraction(7227, 100))


def overset(item: str, needs: str, has: str, **where: Any) -> Overset | None:
    """The `Overset` for lengths as text, or `None` if they are not lengths or the item fits."""
    try:
        need, have = points(needs), points(has)
    except DeclarationError, IndexError:
        return None
    if need <= have:
        return None
    message = f"{item} needs {need:g}pt and has {have:g}pt"
    return Overset(message=message, item=item, needs_pt=need, has_pt=have, over_pt=round(need - have, 3), **where)


__all__ = [
    "Diagnostic",
    "DocumentRefusal",
    "KINDS",
    "Measure",
    "MeasureKind",
    "Measurement",
    "MissingCharacter",
    "MissingFile",
    "NotConverged",
    "OverfullBox",
    "Overset",
    "PackageError",
    "PackageWarning",
    "RerunNeeded",
    "Severity",
    "TexError",
    "UndefinedControlSequence",
    "UndefinedReference",
    "Unexplained",
    "diagnostic_from_dict",
    "overset",
    "points",
]
