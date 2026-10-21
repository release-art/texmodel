"""Turning a component declaration into TeX text (G1): body holes, lints, `\\newcommand`, the package header.

Output is a pure function of the declaration: no timestamps, no hashes, no dict or set ordering.
"""

import dataclasses
import re
from collections.abc import Mapping, Sequence

from ..errors import DeclarationError
from ..types import Colour, Length

_HOLE = re.compile(r"##|#(?P<name>[A-Za-z_]\w*)|#(?P<digit>\d)")
_CONTROL_WORD = re.compile(r"[A-Z][A-Za-z]*")
_TOKEN = re.compile(r"%[^\n]*|\\(?P<word>[A-Za-z@]+)|\\.", re.DOTALL)  # comment | control word | control symbol


def snake(name: str) -> str:
    """`FactGap` -> `fact_gap`."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


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


@dataclasses.dataclass(frozen=True)
class ValueSpec:
    """What the renderer needs to know about one `Value`: its type is its default's type, which decides the TeX."""

    name: str  # the class name
    doc: str
    default: Length | Colour | bool
    kind: str  # "Length" | "Colour" | "Bool", for the provenance comment
    qualname: str
    needs: tuple[str, ...]  # packages it needs (M14)


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


def colour_name(prefix: str, name: str) -> str:
    """`Ink` -> `ac-ink`, `BrandRed` -> `ac-brand-red` (T5); a different namespace from control sequences."""
    return f"{prefix}-{snake(name).replace('_', '-')}"


def bool_names(prefix: str, name: str) -> tuple[str, ...]:
    """The control sequences `\\newif\\if<prefix><name>` defines besides the conditional itself."""
    return (f"{prefix}{name}true", f"{prefix}{name}false")


def render_value(prefix: str, spec: ValueSpec) -> str:
    d, control = spec.default, f"{prefix}{spec.name}"
    if isinstance(d, Length):
        decl = [f"\\newlength{{\\{control}}}", f"\\setlength{{\\{control}}}{{{d}}}"]
    elif isinstance(d, bool):
        decl = [f"\\newif\\if{control}", f"\\{control}{'true' if d else 'false'}"]
    else:
        decl = [f"\\definecolor{{{colour_name(prefix, spec.name)}}}{{{d.model}}}{{{d}}}"]
    lines = [f"% {line}".rstrip() for line in spec.doc.splitlines()]
    return "\n".join([*lines, f"% from {spec.qualname} (value: {spec.kind})", *decl])


def check_references(prefix: str, spec: Spec, declared: Mapping[str, str]) -> None:
    """Every `\\<prefix>Name` in a body is declared in the package (M8, G2); internals and other names are not ours."""
    public = re.compile(rf"{prefix}[A-Z][A-Za-z]*")
    for m in _TOKEN.finditer(spec.body):
        word = m["word"]
        if word and public.fullmatch(word) and word not in declared:
            raise DeclarationError(
                f"{spec.qualname}: body uses \\{word}, which no command or value of this package declares",
                code="TM-M015",
                path=spec.name,
                hint="declare it, or fix the name",
            )


def render_package(
    name: str, version: str, date: str, description: str, stamp: str, requires: Sequence[str], body: str
) -> str:
    packages = "".join(f"\\RequirePackage{{{p}}}\n" for p in requires)
    return (
        f"% {name}.sty -- {stamp}. Do not edit; run `texmodel build`.\n"
        "\\NeedsTeXFormat{LaTeX2e}\n"
        f"\\ProvidesPackage{{{name}}}[{date} v{version} {description or name}]\n"
        f"{chr(10) + packages if packages else ''}"
        f"\n{body}\n"
    )
