"""Turning a component declaration into TeX text (G1): body holes, lints, `\\newcommand`, the package header.

Output is a pure function of the declaration: no timestamps, no hashes, no dict or set ordering.
"""

import dataclasses
import re

from ..errors import DeclarationError

_HOLE = re.compile(r"##|#(?P<name>[A-Za-z_]\w*)|#(?P<digit>\d)")
_CONTROL_WORD = re.compile(r"[A-Z][A-Za-z]*")


@dataclasses.dataclass(frozen=True)
class Arg:
    name: str
    optional: bool = False  # TeX's one optional argument: always first, empty when absent


@dataclasses.dataclass(frozen=True)
class Spec:
    """What the renderer needs to know about one command."""

    name: str  # the class name; the control sequence is prefix + name
    doc: str
    args: tuple[Arg, ...]  # declared order; the optional one (at most one) is first in TeX
    body: str
    origin: str  # "fact.tex" or "inline", for the provenance comment
    qualname: str  # module.Class, for the provenance comment
    unused: tuple[str, ...] = ()


def check_name(name: str, what: str) -> None:
    """A TeX control word has letters only, so a component name has no digits or underscores."""
    if not _CONTROL_WORD.fullmatch(name):
        raise DeclarationError(
            f"{what} name {name!r} must be letters only and start with a capital (it becomes a TeX control word)",
            code="TM-M001",
            path=name,
        )


def tex_arguments(args: tuple[Arg, ...]) -> tuple[Arg, ...]:
    """TeX order: the optional argument first, then the required ones as declared."""
    return (*(a for a in args if a.optional), *(a for a in args if not a.optional))


def rewrite_body(spec: Spec) -> str:
    """Replace `#name` with its `#k`; `##` stays; unknown names, `#1` and unused arguments are refused."""
    position = {a.name: i for i, a in enumerate(tex_arguments(spec.args), start=1)}
    used: set[str] = set()

    def sub(m: re.Match[str]) -> str:
        if m.group(0) == "##":
            return "##"
        if m["digit"]:
            raise DeclarationError(
                f"{spec.qualname}: write #name, not #{m['digit']} (arguments are named by their fields)",
                code="TM-M008",
                path=spec.name,
            )
        if m["name"] not in position:
            raise DeclarationError(
                f"{spec.qualname}: body uses #{m['name']}, which is not a field; fields: {sorted(position)}",
                code="TM-M009",
                path=spec.name,
            )
        used.add(m["name"])
        return f"#{position[m['name']]}"

    text = _HOLE.sub(sub, spec.body)
    if unused := sorted(set(position) - used - set(spec.unused)):
        raise DeclarationError(
            f"{spec.qualname}: body never uses {unused}; use them, or list them in unused=(...)",
            code="TM-M010",
            path=spec.name,
        )
    return text


def check_braces(spec: Spec) -> None:
    """Balanced braces, ignoring escapes and comments: an unbalanced body would swallow the rest of the file."""
    depth = 0
    i, text = 0, spec.body
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 1  # the escaped character is not a brace
        elif c == "%":
            while i < len(text) and text[i] != "\n":
                i += 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                break
        i += 1
    if depth != 0:
        raise DeclarationError(f"{spec.qualname}: unbalanced braces in the body", code="TM-M011", path=spec.name)


def render_command(prefix: str, spec: Spec) -> str:
    check_braces(spec)
    body = rewrite_body(spec).replace("\r\n", "\n").rstrip()
    n = len(spec.args)
    signature = f"[{n}]" + ("[]" if any(a.optional for a in spec.args) else "") if n else ""
    lines = [f"% {line}".rstrip() for line in spec.doc.splitlines()]
    lines += [f"% from {spec.qualname} (body: {spec.origin})", f"\\newcommand{{\\{prefix}{spec.name}}}{signature}{{%"]
    lines += body.splitlines()
    lines.append("}")
    return "\n".join(lines)


def render_package(name: str, version: str, date: str, description: str, stamp: str, commands: str) -> str:
    return (
        f"% {name}.sty -- {stamp}. Do not edit; run `texmodel build`.\n"
        "\\NeedsTeXFormat{LaTeX2e}\n"
        f"\\ProvidesPackage{{{name}}}[{date} v{version} {description or name}]\n"
        f"\n{commands}\n"
    )
