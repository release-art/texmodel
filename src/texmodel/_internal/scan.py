"""Reading the declaration forms of a hand-written package (M9): `\\newcommand`, `\\providecommand`,
`\\DeclareRobustCommand`, `\\newenvironment`, xparse's `\\NewDocumentCommand` family, and the names with no arguments
that `\\newlength` and etoolbox's `\\newtoggle` declare.

Only these forms are read, so a name defined any other way is reported as missing rather than guessed at. An xparse
argument type that texmodel does not model is reported as `?`, which matches no declaration.
"""

import re

_COMMENT = re.compile(r"(?<!\\)%[^\n]*")
_DEFINITION = re.compile(
    r"\\(?:newcommand|providecommand|DeclareRobustCommand|newenvironment)\*?\s*\{?\s*\\?(?P<name>[A-Za-z@]+)\s*\}?\s*"
    r"(?:\[(?P<n>\d)\])?(?P<default>\[)?"
)
_XPARSE = re.compile(
    r"\\(?:New|Renew|Provide|Declare)(?:Expandable)?Document(?:Command|Environment)\s*\{?\s*\\?(?P<name>[A-Za-z@]+)\s*\}?\s*"
)


_NAME_ONLY = re.compile(
    r"\\(?:newlength\s*\{?\s*\\|newtoggle\s*\{)(?P<name>[A-Za-z@]+)"
)  # `\newlength{\w}`, `\newtoggle{t}`


def _group(text: str, start: int) -> tuple[str, int] | None:
    """The balanced `{...}` group at `start`: its content and the index after it."""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    for i in range(start, len(text)):
        depth += text[i] == "{"
        depth -= text[i] == "}"
        if depth == 0:
            return text[start + 1 : i], i + 1
    return None


def xparse_letters(spec: str) -> str:
    """`O{}mm` as `omm`; `d()` and `t*` keep their characters; a type texmodel does not model gives `?`."""
    out: list[str] = []
    i = 0
    while i < len(spec):
        c = spec[i]
        i += 1
        if c.isspace() or c == "+":
            continue
        if c in "mos":
            out.append(c)
        elif c == "O":
            out.append("o")
            i = _skip_default(spec, i)
        elif c in "dDrR" and i + 1 < len(spec):
            out.append(f"{c.lower()}{spec[i]}{spec[i + 1]}")
            i += 2
            if c in "DR":
                i = _skip_default(spec, i)
        elif c == "t" and i < len(spec):
            out.append(f"t{spec[i]}")
            i += 1
        else:
            return "?"
    return "".join(out)


def _skip_default(spec: str, i: int) -> int:
    found = _group(spec, i)
    return found[1] if found else i


def scan_declarations(text: str, prefix: str = "") -> dict[str, str]:
    """`{"cdTalkAboutMe": "[2][]"}`: each name starting with `prefix` that `text` defines, with its signature in the
    form `render.signature` writes (`""` for none, `[n]`, or `[n][]` when the first argument is optional; for an xparse
    definition its argument types as letters). The first definition of a name wins."""
    text = _COMMENT.sub("", text)
    found: list[tuple[int, str, str]] = []
    for m in _DEFINITION.finditer(text):
        found.append((m.start(), m["name"], f"[{m['n']}]" + ("[]" if m["default"] else "") if m["n"] else ""))
    for m in _XPARSE.finditer(text):
        spec = _group(text, m.end())
        found.append((m.start(), m["name"], xparse_letters(spec[0]) if spec else "?"))
    found += [(m.start(), m["name"], "") for m in _NAME_ONLY.finditer(text)]
    out: dict[str, str] = {}
    for _, name, sig in sorted(found):
        if name.startswith(prefix) and name not in out:
            out[name] = sig
    return out
