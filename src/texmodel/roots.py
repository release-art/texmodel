"""Ordered asset roots (C4): the first root holding a name wins, and the rest are reported as shadowed."""

import dataclasses
import logging
import pathlib
from collections.abc import Sequence

from .errors import ValidationError

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Resolution:
    name: str
    path: pathlib.Path
    shadowed: tuple[pathlib.Path, ...] = ()


def resolve(name: str, roots: Sequence[pathlib.Path]) -> Resolution | None:
    """Find `name` under `roots`; the winner is the earliest root. Absolute names and `..` are refused (Z1)."""
    rel = pathlib.PurePosixPath(name)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValidationError(
            f"asset name {name!r} escapes the asset roots", code="TM-C100", hint="use a relative name"
        )
    hits = [root / name for root in roots if (root / name).is_file()]
    if not hits:
        return None
    if len(hits) > 1:
        logger.warning("asset %s exists in %d roots; %s wins over %s", name, len(hits), hits[0], hits[1:])
    return Resolution(name, hits[0], tuple(hits[1:]))


def shadowing(roots: Sequence[pathlib.Path]) -> list[Resolution]:
    """Every name present in more than one root, with the winner and what it hides."""
    seen: dict[str, list[pathlib.Path]] = {}
    for root in roots:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            seen.setdefault(path.relative_to(root).as_posix(), []).append(path)
    return [Resolution(name, paths[0], tuple(paths[1:])) for name, paths in sorted(seen.items()) if len(paths) > 1]
