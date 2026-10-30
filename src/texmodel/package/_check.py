"""What a library defines, and the comparison with what a package declares."""

from collections.abc import Sequence
from typing import NamedTuple

from .._internal.render import (
    canonical,
)
from ..errors import Violation


class Defs(NamedTuple):
    """What a library defines: control sequences with their signatures, and names of other kinds (colours, counters)."""

    controls: dict[str, str]
    others: frozenset[tuple[str, str]]

    def pairs(self) -> list[tuple[str, str]]:
        return [*(("control", n) for n in self.controls), *sorted(self.others)]


def name_shown(kind: str, name: str) -> str:
    return f"\\{name}" if kind == "control" else f"{kind} {name}"


def compare(who: str, lib: str, defs: Defs, wanted: Sequence[tuple[str, str, str]]) -> list[Violation]:
    """`who` wants these names (kind, name, signature) from library `lib`: each must be defined, as declared."""
    out: list[Violation] = []
    for kind, name, want in wanted:
        if (kind, name) not in defs.pairs():
            out.append(
                Violation("TM-C010", who, f"{name_shown(kind, name)} is declared but library {lib} does not define it")
            )
        elif kind == "control" and canonical(defs.controls[name]) != canonical(want):
            out.append(
                Violation(
                    "TM-C011",
                    who,
                    f"{name_shown(kind, name)}: declared {want or 'without arguments'}, library {lib} defines "
                    f"{defs.controls[name] or 'no arguments'}",
                    hint="change the declaration or the library so they agree",
                )
            )
    return out
