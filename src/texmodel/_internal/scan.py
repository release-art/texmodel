"""Reading the declaration forms of a hand-written package (M9): `\\newcommand`, `\\providecommand`, `\\newenvironment`.

Only these forms are read, so a name defined any other way is reported as missing rather than guessed at.
"""

import re

_COMMENT = re.compile(r"(?<!\\)%[^\n]*")
_DEFINITION = re.compile(
    r"\\(?:newcommand|providecommand|newenvironment)\*?\s*\{?\s*\\?(?P<name>[A-Za-z@]+)\s*\}?\s*"
    r"(?:\[(?P<n>\d)\])?(?P<default>\[)?"
)


def scan_declarations(text: str, prefix: str = "") -> dict[str, str]:
    """`{"cdTalkAboutMe": "[2][]"}`: each name starting with `prefix` that `text` defines, with its signature in the
    form `render.signature` writes (`""` for none, `[n]`, or `[n][]` when the first argument is optional). The first
    definition of a name wins."""
    found: dict[str, str] = {}
    for m in _DEFINITION.finditer(_COMMENT.sub("", text)):
        if m["name"].startswith(prefix) and m["name"] not in found:
            found[m["name"]] = f"[{m['n']}]" + ("[]" if m["default"] else "") if m["n"] else ""
    return found
