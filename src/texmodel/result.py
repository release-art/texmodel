"""`CompileResult` (C1): a failed compile is a result, not an exception (E3)."""

import dataclasses
import pathlib
from typing import Any, Self

from .diagnostics import Diagnostic, Measurement, Severity, diagnostic_from_dict
from .errors import CompileError


@dataclasses.dataclass(frozen=True, kw_only=True)
class CompileResult:
    pdf: pathlib.Path | None
    log: pathlib.Path | None
    passes: int
    pages: int | None
    diagnostics: tuple[Diagnostic, ...]
    seconds: float
    engine: str
    engine_version: str
    latexmk_version: str
    image: str | None = None  # None: ran on the host, not in the reference image
    image_digest: str | None = None
    image_revision: str | None = None
    cache_hit: bool = False

    @property
    def ok(self) -> bool:
        return self.pdf is not None and not self.errors

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity is Severity.ERROR)

    @property
    def probes(self) -> dict[str, str]:
        return {d.name: d.value for d in self.diagnostics if isinstance(d, Measurement)}

    def probe(self, name: str) -> str:
        return self.probes[name]

    def raise_for_status(self) -> None:
        if self.ok:
            return
        first = self.errors[0] if self.errors else None
        raise CompileError(
            f"compile failed: {len(self.errors)} error(s)"
            + (f", first: {first.code} {first.message}" if first else ""),
            code=first.code if first else "TM-X099",
            diagnostics=self.diagnostics,
        )

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["pdf"] = str(self.pdf) if self.pdf else None
        data["log"] = str(self.log) if self.log else None
        data["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any], **override: Any) -> Self:
        data = {**data, **override}
        data["pdf"] = pathlib.Path(data["pdf"]) if data["pdf"] else None
        data["log"] = pathlib.Path(data["log"]) if data["log"] else None
        data["diagnostics"] = tuple(diagnostic_from_dict(d) for d in data["diagnostics"])
        return cls(**data)
