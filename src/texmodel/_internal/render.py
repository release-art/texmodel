"""Turning a component declaration into TeX text (G1): body holes, lints, `\\newcommand`, the package header.

Output is a pure function of the declaration: no timestamps, no hashes, no dict or set ordering.
"""

import dataclasses
import re
from collections.abc import Mapping, Sequence
from typing import cast

from ..body import Hole
from ..errors import DeclarationError
from ..types import Choice, Colour, Length, Raw, balanced, escape

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
    raw: bool = False  # a `Raw` field passes through; a `Text` field is escaped (T3)
    choice: type[Choice] | None = None  # a closed set: the member's value is the TeX (T1)


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
    refs: tuple[type, ...] = ()  # components its body calls (§21a 17)


@dataclasses.dataclass(frozen=True)
class EnvSpec:
    """What the renderer needs to know about one environment: two bodies, begin and end."""

    name: str
    doc: str
    args: tuple[Arg, ...]
    begin: str
    end: str
    origin: str  # "card_back.begin.tex + card_back.end.tex" or "inline", for the provenance comment
    qualname: str
    unused: tuple[str, ...] = ()
    refs: tuple[type, ...] = ()


@dataclasses.dataclass(frozen=True)
class ValueSpec:
    """What the renderer needs to know about one `Value`: its type is its default's type, which decides the TeX."""

    name: str  # the class name
    doc: str
    default: Length | Colour | bool | str | None  # None: a `Value[Text]` whose default the hand-written package has
    kind: str  # "Length" | "Colour" | "Bool" | "Text", for the provenance comment
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


def rewrite_body(spec: Spec | EnvSpec, body: str) -> str:
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

    # a comment line is not TeX: its `#` are text (a `Comment` body piece may hold any)
    text = "\n".join(ln if ln.lstrip().startswith("%") else _HOLE.sub(sub, ln) for ln in body.split("\n"))
    if unused := sorted(set(position) - used - set(spec.unused)):
        raise DeclarationError(
            f"{spec.qualname}: body never uses {unused}; use them, or list them in unused=(...)",
            code="TM-M010",
            path=spec.name,
        )
    return text


def check_braces(spec: Spec | EnvSpec, *bodies: str) -> None:
    """Balanced braces: an unbalanced body would swallow the rest of the file."""
    if not all(balanced(b) for b in bodies):
        raise DeclarationError(f"{spec.qualname}: unbalanced braces in the body", code="TM-M011", path=spec.name)


def signature(args: tuple[Arg, ...]) -> str:
    n = len(args)
    return f"[{n}]" + ("[]" if any(a.optional for a in args) else "") if n else ""


def _comment(doc: str) -> list[str]:
    return [f"% {line}".rstrip() for line in doc.splitlines()]


def render_command(prefix: str, spec: Spec) -> str:
    check_braces(spec, spec.body)
    body = rewrite_body(spec, spec.body).replace("\r\n", "\n").rstrip()
    lines = _comment(spec.doc)
    lines += [
        f"% from {spec.qualname} (body: {spec.origin})",
        f"\\newcommand{{\\{prefix}{spec.name}}}{signature(spec.args)}{{%",
    ]
    return "\n".join([*lines, *body.splitlines(), "}"])


def render_environment(prefix: str, spec: EnvSpec) -> str:
    """`\\newenvironment`: arguments belong to the begin body; the end body runs after them and cannot read them."""
    check_braces(spec, spec.begin, spec.end)
    if hole := _HOLE.search(spec.end.replace("##", "")):
        raise DeclarationError(
            f"{spec.qualname}: the end body uses {hole.group(0)}; TeX gives it no arguments; use them in begin",
            code="TM-M018",
            path=spec.name,
        )
    begin = rewrite_body(spec, spec.begin).replace("\r\n", "\n").rstrip()
    end = spec.end.replace("\r\n", "\n").rstrip()
    lines = _comment(spec.doc)
    lines += [
        f"% from {spec.qualname} (body: {spec.origin})",
        f"\\newenvironment{{{prefix}{spec.name}}}{signature(spec.args)}{{%",
        *begin.splitlines(),
        "}{%",
        *end.splitlines(),
        "}",
    ]
    return "\n".join(lines)


def argument(arg: Arg, value: object) -> str:
    """One call argument. `Text` is escaped, `Raw` passes through; a `]` in the optional one is wrapped (T3)."""
    if isinstance(value, Choice):
        value = value.value
    text = f"#{value.name}" if isinstance(value, Hole) else value.tex if isinstance(value, Raw) else escape(str(value))
    if not arg.optional:
        return f"{{{text}}}"
    return f"[{{{text}}}]" if "]" in text else f"[{text}]"


def arguments(args: tuple[Arg, ...], values: Mapping[str, object]) -> str:
    """`[Sound]{A soft woof.}`: the optional argument first, and left out when it is `None`."""
    return "".join(argument(a, values[a.name]) for a in tex_arguments(args) if values[a.name] is not None)


def colour_name(prefix: str, name: str) -> str:
    """`Ink` -> `ac-ink`, `BrandRed` -> `ac-brand-red` (T5); a different namespace from control sequences."""
    return f"{prefix}-{snake(name).replace('_', '-')}"


def bool_names(prefix: str, name: str) -> tuple[str, ...]:
    """The control sequences `\\newif\\if<prefix><name>` defines besides the conditional itself."""
    return (f"{prefix}{name}true", f"{prefix}{name}false")


def setting(prefix: str, name: str, value: Length | Colour | bool | str) -> str:
    """The line that gives a value its content: the default in the `.sty`, a document's `settings=` in the `.tex`."""
    control = f"{prefix}{name}"
    if isinstance(value, str):
        return f"\\renewcommand{{\\{control}}}{{{escape(value)}}}"
    if isinstance(value, Length):
        return f"\\setlength{{\\{control}}}{{{value}}}"
    if isinstance(value, bool):
        return f"\\{control}{'true' if value else 'false'}"
    return f"\\definecolor{{{colour_name(prefix, name)}}}{{{value.model}}}{{{value}}}"


def render_value(prefix: str, spec: ValueSpec) -> str:
    d, control = spec.default, f"{prefix}{spec.name}"
    if isinstance(d, str):
        return "\n".join(
            [
                *_comment(spec.doc),
                f"% from {spec.qualname} (value: Text)",
                f"\\newcommand{{\\{control}}}{{{escape(d)}}}",
            ]
        )
    d = cast("Length | Colour | bool", d)  # Package.value refuses a missing default
    decl = (
        [f"\\newlength{{\\{control}}}"]
        if isinstance(d, Length)
        else [f"\\newif\\if{control}"]
        if isinstance(d, bool)
        else []
    )
    return "\n".join(
        [*_comment(spec.doc), f"% from {spec.qualname} (value: {spec.kind})", *decl, setting(prefix, spec.name, d)]
    )


def undeclared(prefix: str, text: str, declared: Mapping[str, str]) -> list[str]:
    """The `\\<prefix>Name` control words in `text` that `declared` lacks, in order; internals and other names are not
    ours."""
    public = re.compile(rf"{prefix}[A-Z][A-Za-z]*")
    words = (m["word"] for m in _TOKEN.finditer(text))
    return [w for w in words if w and public.fullmatch(w) and w not in declared]


def check_references(prefix: str, spec: Spec | EnvSpec, text: str, declared: Mapping[str, str]) -> None:
    """Every `\\<prefix>Name` in a body is declared in the package (M8, G2)."""
    if words := undeclared(prefix, text, declared):
        raise DeclarationError(
            f"{spec.qualname}: body uses \\{words[0]}, which no command or value of this package declares",
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
