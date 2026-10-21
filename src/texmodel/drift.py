"""Drift (G6): are the committed generated files exactly what the generators would write now?"""

import dataclasses
import pathlib
import re
from collections.abc import Mapping, Sequence

_STAMP = re.compile(r"generated with texmodel (\S+)")


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
        elif path.read_bytes() != want:
            stale_.append(rel)
            written_by = _STAMP.search(path.read_text(encoding="utf-8", errors="replace"))
            if version and written_by and written_by[1] != version:
                notes.append(
                    f"{rel}: generated with texmodel {written_by[1]}, current is {version}: run `texmodel build`"
                )
    present = {p.relative_to(root).as_posix() for glob in owned for p in root.glob(glob) if p.is_file()}
    return Drift(tuple(stale_), tuple(missing_), tuple(sorted(present - expected.keys())), tuple(notes))
