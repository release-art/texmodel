"""The built-in verifier over proof-pdf (the `proof-pdf` extra): PDF/A, PDF/X-4, geometry, colour, proofing."""

import pathlib
from collections.abc import Mapping, Sequence
from typing import Any

from ..diagnostics import Severity
from ..verify import Finding


def _profile(options: Mapping[str, Any]) -> Any:
    from proof_pdf.models import PageGeometry, Profile

    opts = dict(options)
    if "geometry" in opts:
        opts["geometry"] = PageGeometry(**opts["geometry"])
    if "proof_profile" in opts:
        opts["proof_profile"] = pathlib.Path(opts["proof_profile"])
    if "allow_spots" in opts:
        opts["allow_spots"] = tuple(opts["allow_spots"])
    return Profile(**opts)


class ProofPdf:
    """Options are proof_pdf.models.Profile's fields (`geometry` as a table); a file is held to exactly that profile."""

    name = "proof-pdf"

    def unavailable(self, options: Mapping[str, Any]) -> str | None:
        try:
            from proof_pdf import core
        except ImportError:
            return "proof-pdf is not installed (pip install 'texmodel[proof-pdf]')"
        try:
            profile = _profile(options)
        except (TypeError, ValueError) as exc:
            return f"bad proof-pdf options: {exc}"
        missing = core.missing_tools(profile)
        return f"missing tools: {', '.join(missing)}" if missing else None

    async def verify(self, path: pathlib.Path, options: Mapping[str, Any]) -> Sequence[Finding]:
        from proof_pdf import core, models

        report = await core.verify_file(path, _profile(options))
        return [
            Finding(
                f.check, Severity.ERROR if f.severity is models.Severity.ERROR else Severity.WARNING, f.message, f.page
            )
            for f in report.findings
        ]
