"""Contract checks a verifier plugin must pass (L1). Plain asserts, so any test runner can call them."""

import pathlib

from .verify import Profile, Verifier, verify_file


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
