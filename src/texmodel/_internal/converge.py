"""Why a document did not converge (C1a): which `.aux` entries changed between the last two passes."""

import re

_KEYED = re.compile(r"^\\(?:newlabel|bibcite)\{(?P<key>[^}]*)\}|^\\gdef\s*\\(?P<macro>[A-Za-z@]+)")


def _entries(aux: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in aux.splitlines():
        m = _KEYED.match(line)
        out[(m["key"] or m["macro"]) if m else line] = line
    return out


def aux_diff(before: str, after: str) -> tuple[str, ...]:
    """Labels (or whole lines for unkeyed entries) that differ between two `.aux` snapshots, sorted."""
    a, b = _entries(before), _entries(after)
    return tuple(sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k)))
