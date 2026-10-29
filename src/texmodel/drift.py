"""Drift (G6): are the committed generated files exactly what the generators would write now?"""

import dataclasses
import pathlib
import re
from collections.abc import Mapping, Sequence
from typing import Final

_STAMP = re.compile(r"generated with texmodel (\S+)")
_RELEASE = re.compile(r"(\d+)\.(\d+)\.(\d+)")

OUTPUT_CHANGES: Final[Mapping[str, str]] = {
    "0.3.0": r"defaults in definitions, dateless `\ProvidesPackage`, settings after `\usepackage`, 5-decimal colours",
    "0.3.2": "a value written from a float has five decimals",
    "0.8.0": "a document's body is indented two spaces per level of environment",
    "0.10.0": r"`ext.fit` declares its two public lengths with `\newlength`",
    "0.11.0": "a package with a `ColourSpace` declares `cmyk` and `rgb` as l3keys options in an options section",
}
"""The releases whose generated output differs from the release before for the same declarations, and how (G7, K3).
Each has the same text in its `CHANGELOG.md` section, on a line `Output change: <text>.`"""


def stamp(version: str) -> str:
    """The line a generated file's header carries, so `check_drift` can say which version wrote it (G7)."""
    return f"generated with texmodel {version}"


@dataclasses.dataclass(frozen=True)
class Drift:
    stale: tuple[str, ...] = ()  # exists, differs from what would be written (a hand edit, or an older generator)
    missing: tuple[str, ...] = ()  # should exist, does not
    orphaned: tuple[str, ...] = ()  # exists under an owned glob, nothing generates it
    notes: tuple[str, ...] = ()  # e.g. "x.sty: generated with texmodel 0.1.0, current is 0.2.0: run `texmodel build`"

    @property
    def ok(self) -> bool:
        return not (self.stale or self.missing or self.orphaned)


def check_drift(
    expected: Mapping[str, str | bytes],
    root: pathlib.Path,
    owned: Sequence[str] = ("**/*",),
    *,
    version: str | None = None,
) -> Drift:
    """Compare `expected` (path relative to `root` -> content) byte for byte with what is on disk.

    `owned` are globs under `root` that only generators write; any file there that is not expected is orphaned.
    """
    stale_: list[str] = []
    missing_: list[str] = []
    notes: list[str] = []
    for rel, content in sorted(expected.items()):
        path = root / rel
        want = content.encode("utf-8") if isinstance(content, str) else content
        if not path.is_file():
            missing_.append(rel)
        elif (found := path.read_bytes()) != want:
            stale_.append(rel)
            written_by = _STAMP.search(found.decode("utf-8", errors="replace"))
            if version and written_by and written_by[1] != version:
                why = _why(found, want, written_by[1], version)
                notes.append(
                    f"{rel}: generated with texmodel {written_by[1]}, current is {version}; {why}: run `texmodel build`"
                )
    present = {p.relative_to(root).as_posix() for glob in owned for p in root.glob(glob) if p.is_file()}
    return Drift(tuple(stale_), tuple(missing_), tuple(sorted(present - expected.keys())), tuple(notes))


def _release(version: str) -> tuple[int, int, int] | None:
    m = _RELEASE.match(version)
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def _why(found: bytes, want: bytes, old: str, new: str) -> str:
    """What an upgrade from `old` to `new` explains of a stale file: only its version line, the releases between that
    changed output, or nothing, and then the rest is a hand edit or a change to the declarations."""
    if found.replace(stamp(old).encode(), stamp(new).encode()) == want:
        return "only the version line differs"
    since, until = _release(old), _release(new)
    if since is None or until is None:
        return "its version cannot be compared"
    changed = [v for v in OUTPUT_CHANGES if since < (_release(v) or since) <= until]
    if changed:
        return "output changed in " + "; ".join(f"{v} ({OUTPUT_CHANGES[v]})" for v in changed)
    return (
        f"no release since {old} changed generated output, so the rest is a hand edit or a change to the declarations"
    )


__all__ = ["OUTPUT_CHANGES", "Drift", "check_drift", "stamp"]
