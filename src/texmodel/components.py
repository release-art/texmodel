r"""Components (M1): a `Command` is declared as a class; its fields are its arguments, its docstring its documentation.

```python
pkg = Package("acme-cards", prefix="ac")

@pkg.command
class Slot(Command):
    '''A labelled paragraph; the label prints as its heading.'''
    text: Text
    label: Text | None = None      # optional: keyword-only, rendered as TeX's one optional argument
```

A `Value[T]` is a typed setting; its `default` is an instance of `T` and its type decides the TeX (M1a, T4, T5):

```python
@pkg.value
class FactGap(Value[Length]):
    '''Space under each fact.'''
    default = Length("2mm")
```

An `Environment` also holds children, whose order and counts are its grammar (M4); a Doc is plain Python (D1):

```python
@pkg.environment
class CardBack(Environment):
    '''The back face of a card.'''
    children = [Name, Fact.times(2, 3), Slot.times(3)]     # Name: one; Fact: 2 to 3; Slot: 0 to 3
    # also `X.times.any()` (0 or more) and `X.times.at_least_one()` (1 or more)
    begin = r'\begin{minipage}{\linewidth}'
    end = r'\end{minipage}'

pkg.document(CardBack(Name("Rex"), Fact("Friendly & loyal."), Fact("50% of $5")), options=["a4paper"])
```

`Text` fields are escaped on render (T3); a `Raw` field passes TeX through.

A body is TeX, given explicitly: a `body` method returning it (a plain `body = r"..."` string works too), or a
`TemplateRef` to a file. Indentation is removed, so a triple-quoted raw string reads as it will render:

```python
class Title(Command):
    '''A job title.'''
    text: Text

    def body(self):
        return r'''
            \par\noindent{\color{bc-accent}#text}\par
        '''

class Slot(Command):
    '''A labelled paragraph.'''
    text: Text

    def body(self):
        return TemplateRef("slot.tex")      # relative to this module; nothing is looked up by name
```

An environment has `begin` and `end` in the same way. The method is read once, when the class is defined, with no
instance: keep it to constant TeX. Inside a body `#text` is the argument named `text`. A bad declaration is refused when
the class is defined.
"""

import dataclasses
import inspect
import sys
import types
import typing
from collections.abc import Sequence
from typing import Any, ClassVar, dataclass_transform, overload

from ._internal.render import (
    Arg,
    EnvSpec,
    Spec,
    ValueSpec,
    arguments,
    check_name,
)
from .body import (
    Comment,
    Cs,
    Group,
    Hole,
    Library,
    Lit,
    Ref,
    RefKind,
    Seq,
    Syntax,
    TemplateRef,
    TexRaw,
    Whitespace,
    join,
    pieces_of,
    refs_in,
    syntaxes_in,
    template_text,
)
from .errors import DeclarationError, Violation
from .types import CMYK, PDF, RGB, TEXT, Choice, Colour, Gray, Length, Raw, Text

type Node = Command | Environment | Passthrough | Comment
Resolved = TexRaw | Ref | Comment | Group | Seq | Cs | Lit | Hole
Source = tuple[tuple[Resolved, ...], str]  # a body's pieces and where they came from


@dataclasses.dataclass(frozen=True)
class Repeat:
    """How many of one component a grammar allows in a row (M4): `Fact.times(2, 3)`; a bare `Name` is exactly one."""

    kind: type
    lo: int
    hi: int | None

    def __str__(self) -> str:
        return f"{self.lo}-{'any' if self.hi is None else self.hi} {self.kind.__name__}"


@dataclasses.dataclass(frozen=True)
class Anywhere:
    """A grammar term (B3): zero or more `kind` between any two other terms and at both ends, in any number of
    places: `children = [Name, Anywhere(Heading), Fact.times(2, 3)]`. The kind may not also be an ordered term."""

    kind: type

    def __str__(self) -> str:
        return f"{self.kind.__name__} anywhere"


class _Times:
    """`Fact.times(2, 3)`, `Fact.times(3)` (0 to 3), `Fact.times(2, None)` (2 or more), `.any()`, `.at_least_one()`."""

    def __init__(self, kind: type) -> None:
        self.kind = kind

    @overload
    def __call__(self, to: int | None, /) -> Repeat: ...
    @overload
    def __call__(self, from_: int, to: int | None, /) -> Repeat: ...
    def __call__(self, *bounds: int | None) -> Repeat:
        """`times(to)` allows 0 to `to`; `times(from_, to)` allows `from_` to `to`; `to=None` has no upper limit."""
        lo, hi = (0, bounds[0]) if len(bounds) == 1 else bounds if len(bounds) == 2 else (None, None)
        # `type(...) is int` also turns away floats and bools, which slip past the annotations at runtime.
        if type(lo) is not int or lo < 0 or not (hi is None or type(hi) is int and hi >= max(lo, 1)):
            raise DeclarationError(
                f"{self.kind.__name__}.times{bounds}: use (to) or (from, to), ints with 0 <= from <= to and 1 <= to; "
                "to=None means no limit",
                code="TM-M020",
                path=self.kind.__name__,
            )
        return Repeat(self.kind, lo, hi)

    def any(self) -> Repeat:
        """Zero or more."""
        return Repeat(self.kind, 0, None)

    def at_least_one(self) -> Repeat:
        """One or more."""
        return Repeat(self.kind, 1, None)


class _Meta(type):
    """Gives every component class `.times`, so a grammar term reads `Fact.times(2, 3)`."""

    @property
    def times(cls) -> _Times:
        return _Times(cls)


def _document(cls: type) -> str:
    check_name(cls.__name__, "component")
    doc = (cls.__dict__.get("__doc__") or "").strip()
    if not doc:
        raise DeclarationError(f"{cls.__qualname__}: document the component in its docstring", code="TM-M002")
    return doc


def _source(cls: type, name: str) -> Source | None:
    """The class's own `body` / `begin` / `end` as (pieces, origin), or None.

    It is a string, a `TemplateRef` (the file is read now), a `TexRaw`, a `Ref`, a `Comment`, a sequence, iterator or
    generator of those, or a method returning any of them. A field of that name is not a body.
    """
    found: object = cls.__dict__.get(name)
    if found is None or name in inspect.get_annotations(cls):
        return None
    if isinstance(found, types.FunctionType):
        try:
            found = found(None)
        except (AttributeError, TypeError) as exc:
            raise DeclarationError(
                f"{cls.__qualname__}.{name}(): {exc}",
                code="TM-M022",
                path=cls.__name__,
                hint="it is read when the class is defined, so it cannot use self: return constant TeX",
            ) from exc
    if (given := pieces_of(found)) is None:
        got = type(found).__name__
        raise DeclarationError(
            f"{cls.__qualname__}.{name}: must be TeX (a string, a TemplateRef, a TexRaw, a Ref, a Comment, a Group, "
            f"Seq, Cs, Lit or Hole, a sequence of them, or a method returning one), not {got}",
            code="TM-M021",
            path=cls.__name__,
        )
    origins: list[str] = []
    out: list[Resolved] = []
    for piece in given:
        if isinstance(piece, TemplateRef):
            text = template_text(piece, sys.modules[cls.__module__].__file__ or ".", f"{cls.__qualname__}.{name}")
            out.append(TexRaw(text, piece.whitespace, piece.syntax))
            origins.append(piece.path.name)
        else:
            out.append(TexRaw(piece) if isinstance(piece, str) else piece)
            origins.append("inline")
    return tuple(out), " + ".join(dict.fromkeys(origins))


def control_name(cls: type) -> str:
    """The control sequence of a registered component, without the backslash: its `cs`, else its package's prefix and
    its class name."""
    name: str | None = getattr(cls, "__tm_cs__", None)
    if name is None:
        raise DeclarationError(
            f"{cls.__qualname__}: not registered with a package", code="TM-M019", hint="decorate it with @pkg.command"
        )
    return name


class _Node(metaclass=_Meta):
    """What a `Command` and an `Environment` share: declaration data, `repr`, `validate` and `render`."""

    __tm_unused__: ClassVar[tuple[str, ...]]
    __tm_args__: ClassVar[tuple[Arg, ...]]
    __tm_doc__: ClassVar[str]
    __tm_prefix__: ClassVar[str]  # set when a package registers the class
    __tm_cs__: ClassVar[str]  # likewise: the control sequence, see `control_name`
    cs: ClassVar[str | None] = None  # the TeX name, when it is not prefix + class name (`cs = "includegraphics"`)
    syntax: ClassVar[Syntax] = Syntax.LATEX2E  # the names `cs` may have: `Syntax.EXPL3` allows `_` and `:`
    defined_by: ClassVar[Library | None] = None  # the library block that defines it, so it renders no definition
    __tm_package__: ClassVar[object]  # the `Package` it was registered with

    def __repr__(self) -> str:
        return _repr(self)  # pyright: ignore[reportArgumentType]

    def validate(self) -> list[Violation]:
        """Every broken rule at once (E2), with its path into the tree: argument types and, for an environment, the
        children against the grammar (M4)."""
        return _violations(self, type(self).__name__)  # pyright: ignore[reportArgumentType]

    def render(self) -> str:
        """The TeX for this node (`\\acFact{...}`, or `\\begin{acCardBack}` ... `\\end{acCardBack}`): pure and
        deterministic (D2). Raises an `ExceptionGroup` if the node is invalid."""
        return _render(self)  # pyright: ignore[reportArgumentType]


def _as_field(given: object) -> "dataclasses.Field[object]":
    """A default or a `field(...)` as a dataclass field."""
    if isinstance(given, dataclasses.Field):
        return typing.cast("dataclasses.Field[object]", given)
    return typing.cast("dataclasses.Field[object]", dataclasses.field(default=given))


def _build(cls: type[_Node], unused: Sequence[str], *, init: bool) -> None:
    """Turn a declared class into a frozen dataclass whose fields are its arguments."""
    cls.__tm_doc__ = doc = _document(cls)
    cls.__tm_unused__ = tuple(unused)
    if "cs" in cls.__dict__:
        Cs(cls.__dict__["cs"], cls.syntax)  # a control word of the class's syntax (TM-M027)
    # Optional fields are keyword-only (M2): mark them before the dataclass is built.
    for name in inspect.get_annotations(cls):
        if name in cls.__dict__ and not name.startswith("__"):
            spec = _as_field(cls.__dict__[name])
            if spec.default is not dataclasses.MISSING:
                spec.kw_only = True
            setattr(cls, name, spec)
    dataclasses.dataclass(frozen=True, init=init, repr=False)(cls)
    cls.__doc__ = doc
    cls.__tm_args__ = _arguments(cls)  # pyright: ignore[reportArgumentType]


def field(*, renamed_from: str, default: Any = dataclasses.MISSING) -> Any:  # noqa: ANN401  # as dataclasses.field
    """A field that data (`from_dict`) may still name `renamed_from`: `to_dict` and the schema use the field's name, the
    old key loads, and the schema records it as `x-renamed-from` (§21a 15). `default` makes it optional."""
    return dataclasses.field(default=default, metadata={"renamed_from": renamed_from})


@dataclass_transform(frozen_default=True, field_specifiers=(field,))
class Command(_Node):
    """A TeX command (`\\newcommand`) whose arguments are the class's fields."""

    __tm_inline__: ClassVar[Source | None]

    def __init_subclass__(cls, *, unused: Sequence[str] = (), **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.__tm_inline__ = _source(cls, "body")
        _build(cls, unused, init=True)

    @classmethod
    def call(cls, *required: ArgValue, **optional: ArgValue) -> Ref:
        """A body piece that calls this command (§21a 17): the required arguments positionally, the optional one by
        keyword, each a `Hole` (an argument of the component being defined), a `Raw`, a `str` (escaped) or a `Choice`.
        """
        return _ref(cls, RefKind.CALL, required, optional)


@dataclasses.dataclass(frozen=True, init=False, repr=False)
class Environment(_Node):
    """A TeX environment (`\\newenvironment`): fields are its arguments, positional arguments its children."""

    content: tuple[Node, ...]
    children: ClassVar[Sequence[type | Repeat | Anywhere]] = ()  # the grammar: components in order, with counts (M4)
    __tm_inline__: ClassVar[tuple[Source | None, Source | None]]
    __tm_grammar__: ClassVar[tuple[Repeat | Anywhere, ...]]

    def __init_subclass__(cls, *, unused: Sequence[str] = (), **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.__tm_inline__ = (_source(cls, "begin"), _source(cls, "end"))
        cls.__tm_grammar__ = _grammar(cls)
        _build(cls, unused, init=False)

    @classmethod
    def open(cls, **args: ArgValue) -> Ref:
        """A body piece that starts this environment, `\\begin{acBox}`, with its arguments by keyword (§21a 17)."""
        return _ref(cls, RefKind.OPEN, (), args)

    @classmethod
    def close(cls) -> Ref:
        """A body piece that ends this environment, `\\end{acBox}` (§21a 17)."""
        return _ref(cls, RefKind.CLOSE, (), {})

    def __init__(self, *content: Node, **args: str | Raw | None) -> None:
        fields = {f.name: f for f in dataclasses.fields(self) if f.name != "content"}
        if unknown := sorted(set(args) - set(fields)):
            raise TypeError(f"{type(self).__name__}() got unexpected keyword arguments {unknown}")
        if missing := sorted(n for n, f in fields.items() if f.default is dataclasses.MISSING and n not in args):
            raise TypeError(f"{type(self).__name__}() missing keyword arguments {missing}")
        object.__setattr__(self, "content", content)
        for name, f in fields.items():
            object.__setattr__(self, name, args.get(name, f.default))


@dataclasses.dataclass(frozen=True, repr=False)
class Passthrough(_Node):
    """TeX written as it is (B3): a layout `\\vspace` between components. It claims no control sequence; a grammar must
    list it (`Passthrough.times.any()`, or `Anywhere(Passthrough)`) before an environment accepts one."""

    tex: Raw
    __tm_args__: ClassVar[tuple[Arg, ...]] = (Arg("tex", raw=True),)
    __tm_doc__: ClassVar[str] = "TeX written as it is."


type ArgValue = Hole | Raw | str | Choice


def _ref(cls: type, kind: RefKind, required: tuple[ArgValue, ...], optional: dict[str, ArgValue]) -> Ref:
    """Check an argument list against the component's arguments and keep it in declared order (`TM-M026`)."""
    declared = typing.cast("type[Command] | type[Environment]", cls).__tm_args__
    positional = [a for a in declared if not a.optional and not issubclass(cls, Environment)]
    allowed = {a.name for a in declared} - {a.name for a in positional}
    values = {**dict(zip((a.name for a in positional), required, strict=False)), **optional}
    problems = (
        [f"{len(positional)} positional argument(s), got {len(required)}"] if len(required) != len(positional) else []
    )
    problems += [f"unknown argument {n!r}" for n in sorted(set(optional) - allowed)]
    problems += [f"missing argument {a.name!r}" for a in declared if not a.optional and a.name not in values]
    for a in declared:
        value = values.get(a.name)
        if value is not None and not isinstance(value, Hole | (a.choice or (Raw if a.raw else str))):
            problems.append(
                f"{a.name!r} must be a Hole or a {'Choice member' if a.choice else 'Raw' if a.raw else 'str'}"
            )
    if problems and kind is not RefKind.CLOSE:
        raise DeclarationError(
            f"{cls.__name__}.{kind.value}(): " + "; ".join(problems),
            code="TM-M026",
            path=cls.__name__,
        )
    return Ref(cls, kind, tuple(values.get(a.name) for a in declared))


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
    args = arguments(declared, {a.name: v for a, v in zip(declared, ref.values, strict=True)}, syntax)
    return {
        RefKind.CALL: f"\\{name}{args}",
        RefKind.OPEN: f"\\begin{{{name}}}{args}",
        RefKind.CLOSE: f"\\end{{{name}}}",
    }[ref.kind]


def _repr(node: Command | Environment | Passthrough) -> str:
    """The constructor expression that rebuilds the node (D1): required fields positional, optional ones by keyword."""
    shown = [repr(c) for c in node.content] if isinstance(node, Environment) else []
    for a in type(node).__tm_args__:
        v = getattr(node, a.name)
        if a.optional and v is not None:
            shown.append(f"{a.name}={v!r}")
        elif not a.optional and not isinstance(node, Environment):
            shown.append(repr(v))
    return f"{type(node).__name__}({', '.join(shown)})"


def _grammar(cls: type[Environment]) -> tuple[Repeat | Anywhere, ...]:
    terms: list[Repeat | Anywhere] = []
    for item in cls.__dict__.get("children", ()):
        if isinstance(item, type) and issubclass(item, Command | Environment | Passthrough):
            item = Repeat(item, 1, 1)
        if not isinstance(item, Repeat | Anywhere) or not issubclass(item.kind, _Node):
            raise DeclarationError(
                f"{cls.__qualname__}: children must be components, optionally multiplied; got {item!r}",
                code="TM-M020",
                path=cls.__name__,
            )
        terms.append(item)
    floating = {t.kind for t in terms if isinstance(t, Anywhere)}
    if both := sorted(t.kind.__name__ for t in terms if isinstance(t, Repeat) and t.kind in floating):
        raise DeclarationError(
            f"{cls.__qualname__}: {both} is both an ordered term and Anywhere",
            code="TM-M029",
            path=cls.__name__,
            hint="a kind is one or the other",
        )
    return tuple(terms)


def _reserved_type(cls: type) -> DeclarationError:
    return DeclarationError(
        f'{cls.__qualname__}.type: `type` names the component in data (`"type": "Fact"`), so it cannot be a field',
        code="TM-M030",
        path=f"{cls.__name__}.type",
        hint="call the field something else, e.g. `kind`",
    )


def _arguments(cls: type[Command] | type[Environment]) -> tuple[Arg, ...]:
    hints = typing.get_type_hints(cls, include_extras=True)
    args: list[Arg] = []
    for f in dataclasses.fields(cls):  # pyright: ignore[reportArgumentType]
        if f.name == "content":
            continue
        if f.name == "type":
            raise _reserved_type(cls)
        kind = _kind(hints[f.name])
        if kind is None:
            raise DeclarationError(
                f"{cls.__qualname__}.{f.name}: unsupported type {hints[f.name]!r}; "
                "use Text, PdfString, Raw or a Choice, or one of them | None",
                code="TM-M004",
                path=f"{cls.__name__}.{f.name}",
            )
        choice = _choice(cls, f.name, kind) if isinstance(kind, type) else None
        args.append(
            Arg(
                f.name,
                optional=f.default is not dataclasses.MISSING,
                raw=kind == "raw",
                choice=choice,
                pdf=kind == "pdf",
                renamed_from=f.metadata.get("renamed_from"),
            )
        )
    if sum(a.optional for a in args) > 1:
        raise DeclarationError(
            f"{cls.__qualname__}: more than one optional argument (TeX's \\newcommand allows one)",
            code="TM-M003",
            path=cls.__name__,
        )
    return tuple(args)


def _choice(cls: type, field: str, kind: type[Choice]) -> type[Choice]:
    """A `Choice` takes TeX from its members' values: all `Raw` or all `str`, and no two members alike (aliases)."""
    values = [m.value for m in kind]
    if len(values) != len(kind.__members__) or not (
        all(isinstance(v, Raw) for v in values) or all(isinstance(v, str) for v in values)
    ):
        raise DeclarationError(
            f"{cls.__qualname__}.{field}: {kind.__name__} must have members that are all Raw or all str, none an alias",
            code="TM-M024",
            path=f"{cls.__name__}.{field}",
            hint="give each member its TeX as a Raw (passes through) or a str (escaped)",
        )
    return kind


def _kind(hint: Any) -> str | type[Choice] | None:
    """`"text"` for `Text` / `Text | None`, `"raw"` for `Raw` / `Raw | None`, the class for a `Choice` (or `| None`)."""
    members = [
        m for m in (typing.get_args(hint) if isinstance(hint, types.UnionType) else (hint,)) if m is not type(None)
    ]
    if members and all(typing.get_origin(m) is typing.Annotated and TEXT in typing.get_args(m)[1:] for m in members):
        return "text"
    if members and all(typing.get_origin(m) is typing.Annotated and PDF in typing.get_args(m)[1:] for m in members):
        return "pdf"
    if len(members) == 1 and isinstance(members[0], type) and issubclass(members[0], Choice):
        return members[0]
    return "raw" if members and all(m is Raw for m in members) else None


def _violations(node: Command | Environment | Passthrough, path: str) -> list[Violation]:
    cls = type(node)
    out: list[Violation] = []
    for a in cls.__tm_args__:
        v = getattr(node, a.name)
        if not (v is None and a.optional or isinstance(v, a.choice or (Raw if a.raw else str))):
            want = (
                f"one of {list(a.choice.__members__)}"
                if a.choice
                else "Raw"
                if a.raw
                else "PdfString"
                if a.pdf
                else "Text"
            )
            out.append(Violation("TM-C003", f"{path}.{a.name}", f"{a.name}: expected {want}, got {v!r}"))
    if isinstance(node, Environment):
        out += _grammar_violations(node, path)
        for i, child in enumerate(node.content):
            if isinstance(child, Command | Environment | Passthrough):  # pyright: ignore[reportUnnecessaryIsInstance]
                out += _violations(child, f"{path}/{type(child).__name__}[{i}]")
    return out


def _grammar_violations(node: Environment, path: str) -> list[Violation]:
    """Match the children against the grammar: each term takes its run of that component, in order. A `Comment` and
    a child of an `Anywhere` kind are skipped (B3), and every path keeps the child's real position."""
    grammar = type(node).__tm_grammar__
    floating = {t.kind for t in grammar if isinstance(t, Anywhere)}
    ordered = [t for t in grammar if isinstance(t, Repeat)]
    content = [(j, c) for j, c in enumerate(node.content) if not isinstance(c, Comment) and type(c) not in floating]
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


def _render(node: Command | Environment | Passthrough) -> str:
    if violations := _violations(node, type(node).__name__):
        raise ExceptionGroup(f"invalid {type(node).__name__}", [v.error() for v in violations])
    return _emit(node)


def _emit(node: Node) -> str:
    if isinstance(node, Comment):
        return node.render()
    if isinstance(node, Passthrough):
        return node.tex.tex
    cls = type(node)
    name = control_name(cls)
    args = arguments(cls.__tm_args__, {a.name: getattr(node, a.name) for a in cls.__tm_args__})
    if isinstance(node, Command):
        return f"\\{name}{args}"
    return "\n".join([f"\\begin{{{name}}}{args}", *map(_emit, node.content), f"\\end{{{name}}}"])


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
    """A component of an adopted package (M9) or one a library block defines (§21a 12) is only declared: a body would
    never render, so it is refused."""
    if any(sources) and cls.defined_by is not None:
        raise DeclarationError(
            f"{cls.__module__}.{cls.__qualname__}: has a body, but a library block defines it",
            code="TM-M032",
            path=cls.__name__,
            hint="remove the body: the block is the definition",
        )
    if any(sources):
        raise DeclarationError(
            f"{cls.__module__}.{cls.__qualname__}: has a body, but its package is adopted and renders no TeX",
            code="TM-M023",
            path=cls.__name__,
            hint="remove the body: the hand-written package defines it",
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


_KINDS = {
    Length: "Length",
    Colour: "Colour",
    bool: "Bool",
    str: "Text",
    Raw: "Raw",
}  # the closed set `Value[T]` accepts (T2)


class Value[T]:
    """A typed setting: `\\newlength`, `\\definecolor`, `\\newif` or `\\newcommand`, chosen by `T`; `default` is an
    instance of `T`. A `Value[Text]` of an adopted package may leave `default` out: the hand-written package has it."""

    default: T  # not ClassVar[T]: pyright refuses type variables in ClassVar; subclasses assign it in the class body
    needs_packages: ClassVar[tuple[str, ...]] = ()  # data, not mutation: the package takes the union (M14)
    __tm_doc__: ClassVar[str]
    __tm_kind__: ClassVar[str]
    __tm_type__: ClassVar[type | types.UnionType]
    __tm_prefix__: ClassVar[str]

    def __init__(self, value: T) -> None:
        """A document's setting for this value (D1a): `FactGap(Length("3mm"))`, checked against the declared type."""
        if not isinstance(value, type(self).__tm_type__):
            raise DeclarationError(
                f"{type(self).__name__}({value!r}): expected a {type(self).__tm_kind__}", code="TM-M014"
            )
        self.value = value

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.value!r})"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        doc = _document(cls)
        arg = next(
            (typing.get_args(b)[0] for b in cls.__dict__.get("__orig_bases__", ()) if typing.get_origin(b) is Value),
            None,
        )
        if typing.get_origin(arg) is typing.Annotated and TEXT in typing.get_args(arg)[1:]:
            arg = str  # Text
        if arg not in _KINDS:
            raise DeclarationError(
                f"{cls.__qualname__}: base must be Value of Length, Colour, Bool, Text or Raw, not {arg!r}",
                code="TM-M012",
                path=cls.__name__,
            )
        if "default" not in cls.__dict__ and arg not in (str, Raw):
            raise DeclarationError(f"{cls.__qualname__}: no default", code="TM-M013", path=cls.__name__)
        default = cls.__dict__.get("default")
        if default is not None and not isinstance(default, arg):
            raise DeclarationError(
                f"{cls.__qualname__}: default {default!r} is not a {_KINDS[arg]}", code="TM-M014", path=cls.__name__
            )
        implied = ("xcolor",) if isinstance(default, (CMYK, RGB, Gray)) else ()
        cls.__tm_doc__, cls.__tm_kind__, cls.__tm_type__ = doc, _KINDS[arg], arg
        cls.needs_packages = tuple(sorted({*cls.needs_packages, *implied}))


type AnyValue = Value[Length] | Value[Colour] | Value[bool] | Value[Text] | Value[Raw]


def value_spec_of(cls: type[AnyValue]) -> ValueSpec:
    return ValueSpec(
        cls.__name__,
        cls.__tm_doc__,
        cls.__dict__.get("default"),
        cls.__tm_kind__,
        f"{cls.__module__}.{cls.__qualname__}",
        cls.needs_packages,
    )
