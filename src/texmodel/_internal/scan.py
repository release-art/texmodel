"""Reading the declaration forms of a hand-written package (M9): `\\newcommand`, `\\providecommand`,
`\\DeclareRobustCommand`, `\\newenvironment`, xparse's `\\NewDocumentCommand` family, and the names with no arguments
that `\\newlength`, `\\newsavebox`, `\\newfontfamily`, etoolbox's `\\newtoggle` and `\\newif` (with `\\Xtrue` and
`\\Xfalse`) declare. Colours (`\\definecolor`, `\\colorlet`) and counters (`\\newcounter`) are names of their own.

Only these forms are read, so a name defined any other way is reported as missing rather than guessed at. An xparse
argument type that texmodel does not model is reported as `?`, which matches no declaration.
"""

import re

_COMMENT = re.compile(r"(?<!\\)%[^\n]*")
_LITERAL = r"(?<!\\string)(?<!\\noexpand)"  # `\string\providecommand` writes the word out; it defines nothing
_DEFINITION = re.compile(
    rf"{_LITERAL}\\(?:(?:newcommand|providecommand|DeclareRobustCommand)\*?\s*\{{?\s*\\|newenvironment\*?\s*\{{\s*)"
    r"(?P<name>[A-Za-z@]+)\s*\}?\s*(?:\[(?P<n>\d)\])?(?P<default>\[)?"
)
_XPARSE = re.compile(
    rf"{_LITERAL}\\(?:New|Renew|Provide|Declare)(?:Expandable)?Document"
    r"(?:Command\s*\{?\s*\\|Environment\s*\{\s*)(?P<name>[A-Za-z@]+)\s*\}?\s*"
)
_NAME_ONLY = re.compile(
    rf"{_LITERAL}\\(?:(?:newlength|newsavebox|newfontfamily)\s*\{{?\s*\\|newtoggle\s*\{{)(?P<name>[A-Za-z@]+)"
)  # `\newlength{\w}`, `\newsavebox{\b}`, `\newfontfamily\f`, `\newtoggle{t}`
_NEWIF = re.compile(rf"{_LITERAL}\\newif\s*\\if(?P<name>[A-Za-z@]+)")  # defines \ifX, \Xtrue and \Xfalse
_COLOUR = re.compile(r"\\(?:definecolor|colorlet|providecolor)\s*\{(?P<name>[^{}]+)\}")
_COUNTER = re.compile(r"\\newcounter\s*\{(?P<name>[^{}]+)\}")


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


def _newif_names(name: str) -> tuple[str, str, str]:
    return f"if{name}", f"{name}true", f"{name}false"


def scan_colours(text: str) -> frozenset[str]:
    """The colour names `\\definecolor`, `\\colorlet` and `\\providecolor` define: not control sequences."""
    return frozenset(m["name"].strip() for m in _COLOUR.finditer(_COMMENT.sub("", text)))


def scan_counters(text: str) -> frozenset[str]:
    """The counters `\\newcounter` defines: not control sequences either."""
    return frozenset(m["name"].strip() for m in _COUNTER.finditer(_COMMENT.sub("", text)))


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
    found += [(m.start(), n, "") for m in _NEWIF.finditer(text) for n in _newif_names(m["name"])]
    out: dict[str, str] = {}
    for _, name, sig in sorted(found):
        if name.startswith(prefix) and name not in out:
            out[name] = sig
    return out
