"""The rules a node is checked against."""

import typing
from collections.abc import (
    Set as AbstractSet,
)
from typing import TYPE_CHECKING

from .._internal.emit import NodeKind, emit
from .._internal.render import (
    argument_violations,
    tex_arguments,
    written,
)
from ..body import (
    Comment,
)
from ..errors import DeclarationError, Violation
from ..interface import (
    BodyKind,
    ColourName,
    Gap,
)
from ..types import Plate
from ._terms import Anywhere, Repeat

if TYPE_CHECKING:  # the nodes import this module, so it names them for the type checker only
    from ..package import Package
    from ._node import Command, Environment, Passthrough


def violations_of(node: Command | Environment | Passthrough, path: str) -> list[Violation]:
    cls = type(node)
    out: list[Violation] = []
    for a in cls.__tm_args__:
        if why := argument_violations(a, getattr(node, a.name)):
            out.append(Violation("TM-C003", f"{path}.{a.name}", f"{a.name}: {why}"))
    out += _slot_violations(node, path)
    out += _colour_violations(node, path)
    if node.__tm_node__ is NodeKind.ENVIRONMENT:
        env = typing.cast("Environment", node)
        out += _grammar_violations(env, path)
        for check in env.checks:
            out += check(env, path)
        for i, child in enumerate(env.content):
            if hasattr(child, "__tm_node__"):  # a stray value in `content` is the grammar's to report
                out += violations_of(
                    typing.cast("Command | Environment | Passthrough", child), f"{path}/{type(child).__name__}[{i}]"
                )
    return out


def _plates_shown(plates: AbstractSet[str]) -> str:
    """`CMYK`, `K`, `Scodix`: the process plates in press order, then the spots."""
    return "+".join([*(p for p in Plate if p in plates), *sorted(plates - set(Plate))]) if plates else "none"


def _colour_violations(node: Command | Environment | Passthrough, path: str) -> list[Violation]:
    """A colour argument names colours its package declares (`TM-C022`) and mixes only colours that ink the same plates
    (`TM-C024`); an expression that is not `name!50!name` is `TM-C023`. A node outside a package is not checked."""
    package = typing.cast("Package | None", getattr(type(node), "__tm_package__", None))
    if package is None:
        return []
    known = package.colour_constraints()
    out: list[Violation] = []
    for a in type(node).__tm_args__:
        value = getattr(node, a.name)
        if a.body.kind is not BodyKind.COLOUR_NAME or not isinstance(value, str) or value == "":
            continue
        where = f"{path}.{a.name}"
        try:
            names = ColourName(value).names
        except DeclarationError as exc:
            out.append(Violation("TM-C023", where, str(exc), hint="name, name!50 or name!50!name"))
            continue
        out += [
            Violation(
                "TM-C022",
                where,
                f"{a.name}: colour {n!r} is not declared by package {package.name}",
                hint="declare a colour value, define it in a library, or use an xcolor base name",
            )
            for n in names
            if n not in known
        ]
        mixed = {n: known[n] for n in dict.fromkeys(names) if known.get(n) is not None}
        if len({known[n] for n in mixed}) > 1:
            shown = ", ".join(f"{n} {_plates_shown(mixed[n] or frozenset())}" for n in mixed)
            out.append(
                Violation(
                    "TM-C024",
                    where,
                    f"{a.name}: {value!r} mixes colours that ink different plates ({shown})",
                    hint="both ends of a mix may ink the same plates and no others",
                )
            )
    return out


def _slot_violations(node: Command | Environment | Passthrough, path: str) -> list[Violation]:
    """Slots that are written together or not at all (`TM-C004`), and a skipped slot that is refused (`TM-C005`)."""
    out: list[Violation] = []
    ordered = tex_arguments(type(node).__tm_args__)
    shown = [written(a, getattr(node, a.name)) for a in ordered]
    for group in dict.fromkeys(a.group for a in ordered if a.group is not None):
        members = [(a, s) for a, s in zip(ordered, shown, strict=True) if a.group is group]
        if 0 < sum(s for _, s in members) < len(members):
            unset = [a.name for a, s in members if not s]
            out.append(
                Violation(
                    "TM-C004", path, f"group {group.name!r}: {unset} not set, the others are", hint="set all or none"
                )
            )
    for i, a in enumerate(ordered):
        if (
            not shown[i]
            and a.optional
            and not a.token
            and a.fill is Gap.REFUSE
            and any(s and b.optional and not b.token for s, b in zip(shown[i + 1 :], ordered[i + 1 :], strict=True))
        ):
            out.append(
                Violation("TM-C005", f"{path}.{a.name}", f"{a.name} is left out but a later optional argument is set")
            )
    return out


def _grammar_violations(node: Environment, path: str) -> list[Violation]:
    """Match the children against the grammar: each term takes its run of that component, in order. A `Comment` and
    a child of an `Anywhere` kind are skipped (B3), and every path keeps the child's real position."""
    grammar = type(node).__tm_grammar__
    floating = {t.kind for t in grammar if isinstance(t, Anywhere)}
    ordered = [t for t in grammar if isinstance(t, Repeat)]
    abstract = tuple(k for k in floating if getattr(k, "__tm_abstract__", False))
    content = [
        (j, c)
        for j, c in enumerate(node.content)
        if not isinstance(c, Comment) and type(c) not in floating and not isinstance(c, abstract)
    ]
    allowed = ", ".join(map(str, grammar)) or "nothing"
    out: list[Violation] = []
    i = 0
    for term in ordered:
        n = 0
        while i < len(content) and (term.hi is None or n < term.hi) and type(content[i][1]) is term.kind:
            i, n = i + 1, n + 1
        if n < term.lo:
            out.append(
                Violation(
                    "TM-C002", path, f"{type(node).__name__}: expected {term}, found {n}", hint=f"allowed: {allowed}"
                )
            )
    for j, child in content[i:]:
        found = type(child).__name__
        out.append(
            Violation(
                "TM-C001",
                f"{path}/{found}[{j}]",
                f"{type(node).__name__}: {found} is not allowed here",
                hint=f"allowed, in order: {allowed}",
            )
        )
    return out


def render_of(node: Command | Environment | Passthrough) -> str:
    if violations := violations_of(node, type(node).__name__):
        raise ExceptionGroup(f"invalid {type(node).__name__}", [v.error() for v in violations])
    return emit(node)
