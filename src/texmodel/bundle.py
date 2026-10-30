"""`bundle` and `install` (G5): copy a manifest of files somewhere, refuse if any is missing, check it is current.

An `Item` is one file: where it comes from, where it goes (relative to the destination), and why. Where things go is
the caller's policy (a typeface must sit at a document's root because luaotfload reads no search path; a package can
sit anywhere kpathsea looks), so this module decides nothing about layout. To prove a bundle self-contained, compile it
with no asset roots and no font directories (texmodel.run can).
"""

import dataclasses
import pathlib
import shutil
from collections.abc import Mapping, Sequence

from .errors import DeclarationError


@dataclasses.dataclass(frozen=True)
class Item:
    source: pathlib.Path  # absolute, in the tree being exported
    dest: pathlib.Path  # relative to the bundle or target root
    why: str = ""  # one line, for the report and a README

    @property
    def present(self) -> bool:
        return self.source.is_file()


def missing(items: Sequence[Item]) -> tuple[Item, ...]:
    return tuple(item for item in items if not item.present)


def stale(items: Sequence[Item], target: pathlib.Path) -> tuple[Item, ...]:
    """The items `target` does not already hold, byte for byte. Content, not timestamps: a checkout rewrites mtimes."""
    return tuple(
        item
        for item in items
        if not ((target / item.dest).is_file() and (target / item.dest).read_bytes() == item.source.read_bytes())
    )


def _inside(root: pathlib.Path, rel: pathlib.PurePath) -> pathlib.Path:
    if rel.is_absolute() or ".." in rel.parts:
        raise DeclarationError(f"{rel}: destination escapes {root}", code="TM-B002", hint="use a relative path")
    return root / rel


def write(
    items: Sequence[Item], destination: pathlib.Path, generated: Mapping[str, str] | None = None
) -> tuple[pathlib.Path, ...]:
    """Copy `items` into `destination` and write `generated` (path -> text) beside them.

    Refuses the whole export if any source is absent: a bundle that looks finished but lacks a file builds on a machine
    that happens to have it installed, and fails everywhere else.
    """
    if absent := missing(items):
        names = "\n".join(f"  {item.source}" for item in absent)
        raise DeclarationError(f"{destination}: not written, missing sources:\n{names}", code="TM-B001")
    written: list[pathlib.Path] = []
    for item in items:
        target = _inside(destination, item.dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item.source, target)  # the bytes, not a carried-over mtime
        written.append(target)
    for rel, text in (generated or {}).items():
        target = _inside(destination, pathlib.PurePosixPath(rel))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(target)
    return tuple(written)


__all__ = ["Item", "missing", "stale", "write"]
