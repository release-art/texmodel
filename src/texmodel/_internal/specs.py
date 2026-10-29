"""What the renderer reads from a declared class (M8): a command's or environment's `Spec` with its body, a value's
`ValueSpec`, and the control sequence a registered class is called by. Read from the class's attributes only, so the
component classes import this module, not the other way round."""

import typing
from typing import TYPE_CHECKING

from ..body import Ref, RefKind, Seq, Syntax, Whitespace
from ..errors import DeclarationError
from ..types import Raw, ValueKind
from .inline import inline_text, join
from .pieces import refs_in, syntaxes_in
from .render import EnvSpec, Spec, ValueSpec, arguments

if TYPE_CHECKING:
    from ..components import AnyValue, Command, Environment, Source


def control_name(cls: type) -> str:
    """The control sequence of a registered component or value, without the backslash: its `cs`, else its package's
    prefix and its class name. A colour is not a control sequence (`TM-M042`)."""
    name: str | None = getattr(cls, "__tm_cs__", None)
    if name is None and isinstance(getattr(cls, "__tm_kind__", None), ValueKind) and hasattr(cls, "__tm_prefix__"):
        raise DeclarationError(
            f"{cls.__qualname__}: a colour has no control sequence",
            code="TM-M042",
            hint="its name is `colour_name`, else prefix-kebab (xcolor's namespace)",
        )
    if name is None:
        raise DeclarationError(
            f"{cls.__qualname__}: not registered with a package", code="TM-M019", hint="decorate it with @pkg.command"
        )
    return name


def _ref_text(ref: Ref, owner: str, syntax: Syntax) -> str:
    """The TeX a reference stands for. The target must be registered: its prefix is part of the name."""
    if not hasattr(ref.target, "__tm_cs__"):
        raise DeclarationError(
            f"{owner}: calls {ref.target.__name__}, which is not registered with a package",
            code="TM-M019",
            path=owner,
            hint="register it (decorate it with its package's command/environment) before the body that calls it",
        )
    name = control_name(ref.target)
    declared = typing.cast("type[Command] | type[Environment]", ref.target).__tm_args__

    def flat(value: object) -> object:  # a call inside an argument is written where it stands
        if isinstance(value, Ref | Seq):
            return Raw(inline_text(value, lambda inner: _ref_text(inner, owner, syntax), syntax))
        return value

    args = arguments(declared, {a.name: flat(v) for a, v in zip(declared, ref.values, strict=True)}, syntax)
    return {
        RefKind.CALL: f"\\{name}{args}",
        RefKind.OPEN: f"\\begin{{{name}}}{args}",
        RefKind.CLOSE: f"\\end{{{name}}}",
    }[ref.kind]


def _syntax(cls: type, *sources: Source | None) -> Syntax:
    """The one syntax of a body, or of an environment's two (`TM-M031` if its pieces differ); `LATEX2E` if none says."""
    found = dict.fromkeys(s for src in sources if src for piece in src[0] for s in syntaxes_in(piece))
    if len(found) > 1:
        raise DeclarationError(
            f"{cls.__qualname__}: the body mixes {' and '.join(s.value for s in found)}",
            code="TM-M031",
            path=cls.__name__,
            hint="a body is written in one syntax: give every TexRaw, TemplateRef and Cs the same `syntax=`",
        )
    return next(iter(found), Syntax.LATEX2E)


def _required(
    cls: type, found: Source | None, option: str, default: Whitespace, syntax: Syntax
) -> tuple[str, str, tuple[type, ...]]:
    """The text of a body (the package's default whitespace policy for pieces that have none), its origin and the
    components it calls."""
    if found is None:
        raise DeclarationError(
            f"{cls.__module__}.{cls.__qualname__}: no {option}",
            code="TM-M006",
            path=cls.__name__,
            hint=f'define `{option}` as a string, a TemplateRef("file.tex"), a TexRaw, or a method returning one',
        )
    owner = f"{cls.__qualname__}.{option}"
    text = join(found[0], default, owner, lambda ref: _ref_text(ref, owner, syntax), syntax)
    return text, found[1], tuple(dict.fromkeys(r.target for p in found[0] for r in refs_in(p)))


def _declared_only(cls: "type[Command] | type[Environment]", *sources: Source | None) -> None:
    """A component of an adopted package (M9) or one a library block defines (§21) is only declared: another source
    has its TeX, so a body would never render and is refused."""
    if any(sources):
        who = "a library block" if cls.defined_by is not None else "the hand-written package (it is adopted)"
        raise DeclarationError(
            f"{cls.__module__}.{cls.__qualname__}: has a body, but {who} defines it",
            code="TM-M032",
            path=cls.__name__,
            hint="remove the body: the other source is the definition",
        )


def spec_of(cls: type[Command], *, declared_only: bool = False, whitespace: Whitespace = Whitespace.KEEP) -> Spec:
    """The declaration as the renderer sees it, with its body (M8); `declared_only` (M9) has none."""
    declared_only = declared_only or cls.defined_by is not None
    if declared_only:
        _declared_only(cls, cls.__tm_inline__)
    syntax = _syntax(cls, cls.__tm_inline__)
    body, origin, refs = (
        ("", "declared", ()) if declared_only else _required(cls, cls.__tm_inline__, "body", whitespace, syntax)
    )
    return Spec(
        cls.__name__,
        cls.__tm_doc__,
        cls.__tm_args__,
        body,
        origin,
        f"{cls.__module__}.{cls.__qualname__}",
        cls.__tm_unused__,
        refs,
        cls.__dict__.get("cs"),
        syntax,
    )


def env_spec_of(
    cls: type[Environment], *, declared_only: bool = False, whitespace: Whitespace = Whitespace.KEEP
) -> EnvSpec:
    """As `spec_of`, with two bodies: `begin` and `end`."""
    declared_only = declared_only or cls.defined_by is not None
    syntax = _syntax(cls, *cls.__tm_inline__)
    if declared_only:
        _declared_only(cls, *cls.__tm_inline__)
        begin = end = ""
        origin, refs = "declared", ()
    else:
        begin, begin_origin, begin_refs = _required(cls, cls.__tm_inline__[0], "begin", whitespace, syntax)
        end, end_origin, end_refs = _required(cls, cls.__tm_inline__[1], "end", whitespace, syntax)
        origin = " + ".join(dict.fromkeys((begin_origin, end_origin)))
        refs = tuple(dict.fromkeys((*begin_refs, *end_refs)))
    return EnvSpec(
        cls.__name__,
        cls.__tm_doc__,
        cls.__tm_args__,
        begin,
        end,
        origin,
        f"{cls.__module__}.{cls.__qualname__}",
        cls.__tm_unused__,
        refs,
        cls.__dict__.get("cs"),
        syntax,
    )


def value_spec_of(cls: type[AnyValue]) -> ValueSpec:
    return ValueSpec(
        cls.__name__,
        cls.__tm_doc__,
        cls.__dict__.get("default"),
        cls.__tm_kind__,
        f"{cls.__module__}.{cls.__qualname__}",
        cls.needs_packages,
        cls.colour_name,
        cls.cs,
        cls.meta,
    )
