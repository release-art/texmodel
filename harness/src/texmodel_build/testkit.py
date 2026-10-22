"""Contract checks a verifier plugin must pass (L1). Plain asserts, so any test runner can call them."""

import pathlib
import tempfile
from collections.abc import Mapping

from .compiler import Compiler
from .diagnostics import Measurement
from .verify import Profile, Verifier, verify_file


def run_probes(compiler: Compiler, tex: str, files: Mapping[str, str] | None = None) -> list[Measurement]:
    """Compile `tex` and return its `texmodel:probe:` lines in log order (§21a 20, C5a). `files` are written beside it
    first (path -> text: the `.sty` the document loads); the build directory is removed afterwards. A document that
    does not compile raises `CompileError`, so a test never reads probes from a broken run."""
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp).resolve() / "src"
        for rel, text in {**(files or {}), "probe.tex": tex}.items():
            path = work / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        result = compiler.compile(work / "probe.tex", pathlib.Path(tmp).resolve() / "out")
        result.raise_for_status()
        return [d for d in result.diagnostics if isinstance(d, Measurement)]


def check_verifier_contract(verifier: Verifier, tmp_path: pathlib.Path) -> None:
    """A verifier names itself, and a missing file or an unavailable tool fails; neither passes nor raises."""
    assert isinstance(verifier.name, str) and verifier.name, "a verifier needs a non-empty name"
    available = {verifier.name: verifier}
    profile = Profile(checks=(verifier.name,))
    report = verify_file(tmp_path / "does-not-exist", profile, available)
    assert not report.ok, "a missing file must fail, not pass"
    why = verifier.unavailable({})
    assert why is None or isinstance(why, str), "unavailable() returns a reason or None"
    if why is not None:
        present = tmp_path / "present"
        present.write_bytes(b"x")
        assert not verify_file(present, profile, available).ok, "an unavailable verifier must fail the file"
