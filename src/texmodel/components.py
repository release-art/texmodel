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
from pathlib import Path
from typing import Any, ClassVar, dataclass_transform, overload

from ._internal.render import (
    Arg,
    EnvSpec,
    Spec,
    ValueSpec,
    arguments,
    check_name,
)
from .body import TemplateRef, TexRaw, Whitespace, join, pieces_of
from .errors import DeclarationError, Violation
from .types import CMYK, RGB, TEXT, Choice, Colour, Gray, Length, Raw, Text

type Node = Command | Environment


@dataclasses.dataclass(frozen=True)
class Repeat:
    """How many of one component a grammar allows in a row (M4): `Fact.times(2, 3)`; a bare `Name` is exactly one."""

    kind: type
    lo: int
    hi: int | None

    def __str__(self) -> str:
        return f"{self.lo}-{'any' if self.hi is None else self.hi} {self.kind.__name__}"


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


def _source(cls: type, name: str) -> tuple[tuple[TexRaw, ...], str] | None:
    """The class's own `body` / `begin` / `end` as (pieces, origin), or None.

    It is a string, a `TemplateRef` (the file is read now), a `TexRaw`, a sequence, iterator or generator of those, or a
    method returning any of them. A field of that name is not a body.
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
            f"{cls.__qualname__}.{name}: must be TeX (a string, a TemplateRef, a TexRaw, a sequence of them, "
            f"or a method returning one), not {got}",
            code="TM-M021",
            path=cls.__name__,
        )
    origins: list[str] = []
    out: list[TexRaw] = []
    for piece in given:
        if isinstance(piece, TemplateRef):
            path = (
                piece.path
                if piece.path.is_absolute()
                else Path(sys.modules[cls.__module__].__file__ or ".").parent / piece.path
            )
            try:
                out.append(TexRaw(path.read_text(encoding="utf-8"), piece.whitespace))
            except OSError as exc:
                raise DeclarationError(
                    f"{cls.__qualname__}.{name}: cannot read {path}: {exc.strerror}", code="TM-M005", path=cls.__name__
                ) from exc
            origins.append(piece.path.name)
        else:
            out.append(piece if isinstance(piece, TexRaw) else TexRaw(piece))
            origins.append("inline")
    return tuple(out), " + ".join(dict.fromkeys(origins))


def _prefix(cls: type) -> str:
    prefix: str | None = getattr(cls, "__tm_prefix__", None)
    if prefix is None:
        raise DeclarationError(
            f"{cls.__qualname__}: not registered with a package", code="TM-M019", hint="decorate it with @pkg.command"
        )
    return prefix


class _Node(metaclass=_Meta):
    """What a `Command` and an `Environment` share: declaration data, `repr`, `validate` and `render`."""

    __tm_unused__: ClassVar[tuple[str, ...]]
    __tm_args__: ClassVar[tuple[Arg, ...]]
    __tm_doc__: ClassVar[str]
    __tm_prefix__: ClassVar[str]  # set when a package registers the class

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


def _build(cls: type[_Node], unused: Sequence[str], *, init: bool) -> None:
    """Turn a declared class into a frozen dataclass whose fields are its arguments."""
    cls.__tm_doc__ = doc = _document(cls)
    cls.__tm_unused__ = tuple(unused)
    # Optional fields are keyword-only (M2): mark them before the dataclass is built.
    for name in inspect.get_annotations(cls):
        if name in cls.__dict__ and not name.startswith("__"):
            setattr(cls, name, dataclasses.field(default=cls.__dict__[name], kw_only=True))
    dataclasses.dataclass(frozen=True, init=init, repr=False)(cls)
    cls.__doc__ = doc
    cls.__tm_args__ = _arguments(cls)  # pyright: ignore[reportArgumentType]


@dataclass_transform(frozen_default=True)
class Command(_Node):
    """A TeX command (`\\newcommand`) whose arguments are the class's fields."""

    __tm_inline__: ClassVar[tuple[tuple[TexRaw, ...], str] | None]

    def __init_subclass__(cls, *, unused: Sequence[str] = (), **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.__tm_inline__ = _source(cls, "body")
        _build(cls, unused, init=True)


@dataclasses.dataclass(frozen=True, init=False, repr=False)
class Environment(_Node):
    """A TeX environment (`\\newenvironment`): fields are its arguments, positional arguments its children."""

    content: tuple[Node, ...]
    children: ClassVar[Sequence[type | Repeat]] = ()  # the grammar: components in order, with counts (M4)
    __tm_inline__: ClassVar[tuple[tuple[tuple[TexRaw, ...], str] | None, tuple[tuple[TexRaw, ...], str] | None]]
    __tm_grammar__: ClassVar[tuple[Repeat, ...]]

    def __init_subclass__(cls, *, unused: Sequence[str] = (), **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.__tm_inline__ = (_source(cls, "begin"), _source(cls, "end"))
        cls.__tm_grammar__ = _grammar(cls)
        _build(cls, unused, init=False)

    def __init__(self, *content: Node, **args: str | Raw | None) -> None:
        fields = {f.name: f for f in dataclasses.fields(self) if f.name != "content"}
        if unknown := sorted(set(args) - set(fields)):
            raise TypeError(f"{type(self).__name__}() got unexpected keyword arguments {unknown}")
        if missing := sorted(n for n, f in fields.items() if f.default is dataclasses.MISSING and n not in args):
            raise TypeError(f"{type(self).__name__}() missing keyword arguments {missing}")
        object.__setattr__(self, "content", content)
        for name, f in fields.items():
            object.__setattr__(self, name, args.get(name, f.default))


def _repr(node: Node) -> str:
    """The constructor expression that rebuilds the node (D1): required fields positional, optional ones by keyword."""
    shown = [repr(c) for c in node.content] if isinstance(node, Environment) else []
    for a in type(node).__tm_args__:
        v = getattr(node, a.name)
        if a.optional and v is not None:
            shown.append(f"{a.name}={v!r}")
        elif not a.optional and isinstance(node, Command):
            shown.append(repr(v))
    return f"{type(node).__name__}({', '.join(shown)})"


def _grammar(cls: type[Environment]) -> tuple[Repeat, ...]:
    terms: list[Repeat] = []
    for item in cls.__dict__.get("children", ()):
        if isinstance(item, type) and issubclass(item, Command | Environment):
            item = Repeat(item, 1, 1)
        if not isinstance(item, Repeat):
            raise DeclarationError(
                f"{cls.__qualname__}: children must be components, optionally multiplied; got {item!r}",
                code="TM-M020",
                path=cls.__name__,
            )
        terms.append(item)
    return tuple(terms)


def _arguments(cls: type[Command] | type[Environment]) -> tuple[Arg, ...]:
    hints = typing.get_type_hints(cls, include_extras=True)
    args: list[Arg] = []
    for f in dataclasses.fields(cls):  # pyright: ignore[reportArgumentType]
        if f.name == "content":
            continue
        kind = _kind(hints[f.name])
        if kind is None:
            raise DeclarationError(
                f"{cls.__qualname__}.{f.name}: unsupported type {hints[f.name]!r}; "
                "use Text, Raw or a Choice, or one of them | None",
                code="TM-M004",
                path=f"{cls.__name__}.{f.name}",
            )
        choice = _choice(cls, f.name, kind) if isinstance(kind, type) else None
        args.append(Arg(f.name, optional=f.default is not dataclasses.MISSING, raw=kind == "raw", choice=choice))
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
    if len(members) == 1 and isinstance(members[0], type) and issubclass(members[0], Choice):
        return members[0]
    return "raw" if members and all(m is Raw for m in members) else None


def _violations(node: Node, path: str) -> list[Violation]:
    cls = type(node)
    out: list[Violation] = []
    for a in cls.__tm_args__:
        v = getattr(node, a.name)
        if not (v is None and a.optional or isinstance(v, a.choice or (Raw if a.raw else str))):
            want = f"one of {list(a.choice.__members__)}" if a.choice else "Raw" if a.raw else "Text"
            out.append(Violation("TM-C003", f"{path}.{a.name}", f"{a.name}: expected {want}, got {v!r}"))
    if isinstance(node, Environment):
        out += _grammar_violations(node, path)
        for i, child in enumerate(node.content):
            if isinstance(child, Command | Environment):  # pyright: ignore[reportUnnecessaryIsInstance]
                out += _violations(child, f"{path}/{type(child).__name__}[{i}]")
    return out


def _grammar_violations(node: Environment, path: str) -> list[Violation]:
    """Match the children against the grammar: each term takes its run of that component, in order."""
    grammar, content = type(node).__tm_grammar__, node.content
    allowed = ", ".join(map(str, grammar)) or "nothing"
    out: list[Violation] = []
    i = 0
    for term in grammar:
        n = 0
        while i < len(content) and (term.hi is None or n < term.hi) and type(content[i]) is term.kind:
            i, n = i + 1, n + 1
        if n < term.lo:
            out.append(
                Violation(
                    "TM-C002", path, f"{type(node).__name__}: expected {term}, found {n}", hint=f"allowed: {allowed}"
                )
            )
    for j in range(i, len(content)):
        found = type(content[j]).__name__
        out.append(
            Violation(
                "TM-C001",
                f"{path}/{found}[{j}]",
                f"{type(node).__name__}: {found} is not allowed here",
                hint=f"allowed, in order: {allowed}",
            )
        )
    return out


def _render(node: Node) -> str:
    if violations := _violations(node, type(node).__name__):
        raise ExceptionGroup(f"invalid {type(node).__name__}", [v.error() for v in violations])
    return _emit(node)


def _emit(node: Node) -> str:
    cls = type(node)
    name = f"{_prefix(cls)}{cls.__name__}"
    args = arguments(cls.__tm_args__, {a.name: getattr(node, a.name) for a in cls.__tm_args__})
    if isinstance(node, Command):
        return f"\\{name}{args}"
    return "\n".join([f"\\begin{{{name}}}{args}", *map(_emit, node.content), f"\\end{{{name}}}"])


Source = tuple[tuple[TexRaw, ...], str]


def _required(cls: type, found: Source | None, option: str, default: Whitespace) -> tuple[str, str]:
    """The text of a body, with the package's default whitespace policy for pieces that have none, and its origin."""
    if found is None:
        raise DeclarationError(
            f"{cls.__module__}.{cls.__qualname__}: no {option}",
            code="TM-M006",
            path=cls.__name__,
            hint=f'define `{option}` as a string, a TemplateRef("file.tex"), a TexRaw, or a method returning one',
        )
    return join(found[0], default, f"{cls.__qualname__}.{option}"), found[1]


def _declared_only(cls: type, *sources: Source | None) -> None:
    """A component of an adopted package is only declared: a body would never render, so it is refused (M9)."""
    if any(sources):
        raise DeclarationError(
            f"{cls.__module__}.{cls.__qualname__}: has a body, but its package is adopted and renders no TeX",
            code="TM-M023",
            path=cls.__name__,
            hint="remove the body: the hand-written package defines it",
        )


def spec_of(cls: type[Command], *, declared_only: bool = False, whitespace: Whitespace = Whitespace.KEEP) -> Spec:
    """The declaration as the renderer sees it, with its body (M8); `declared_only` (M9) has none."""
    if declared_only:
        _declared_only(cls, cls.__tm_inline__)
    body, origin = ("", "declared") if declared_only else _required(cls, cls.__tm_inline__, "body", whitespace)
    return Spec(
        cls.__name__,
        cls.__tm_doc__,
        cls.__tm_args__,
        body,
        origin,
        f"{cls.__module__}.{cls.__qualname__}",
        cls.__tm_unused__,
    )


def env_spec_of(
    cls: type[Environment], *, declared_only: bool = False, whitespace: Whitespace = Whitespace.KEEP
) -> EnvSpec:
    """As `spec_of`, with two bodies: `begin` and `end`."""
    if declared_only:
        _declared_only(cls, *cls.__tm_inline__)
        begin = end = ""
        origin = "declared"
    else:
        begin, begin_origin = _required(cls, cls.__tm_inline__[0], "begin", whitespace)
        end, end_origin = _required(cls, cls.__tm_inline__[1], "end", whitespace)
        origin = " + ".join(dict.fromkeys((begin_origin, end_origin)))
    return EnvSpec(
        cls.__name__,
        cls.__tm_doc__,
        cls.__tm_args__,
        begin,
        end,
        origin,
        f"{cls.__module__}.{cls.__qualname__}",
        cls.__tm_unused__,
    )


_KINDS = {Length: "Length", Colour: "Colour", bool: "Bool", str: "Text"}  # the closed set `Value[T]` accepts (T2)


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
                f"{cls.__qualname__}: base must be Value of Length, Colour, Bool or Text, not {arg!r}",
                code="TM-M012",
                path=cls.__name__,
            )
        if "default" not in cls.__dict__ and arg is not str:
            raise DeclarationError(f"{cls.__qualname__}: no default", code="TM-M013", path=cls.__name__)
        default = cls.__dict__.get("default")
        if default is not None and not isinstance(default, arg):
            raise DeclarationError(
                f"{cls.__qualname__}: default {default!r} is not a {_KINDS[arg]}", code="TM-M014", path=cls.__name__
            )
        implied = ("xcolor",) if isinstance(default, (CMYK, RGB, Gray)) else ()
        cls.__tm_doc__, cls.__tm_kind__, cls.__tm_type__ = doc, _KINDS[arg], arg
        cls.needs_packages = tuple(sorted({*cls.needs_packages, *implied}))


def value_spec_of(cls: type[Value[Length] | Value[Colour] | Value[bool] | Value[Text]]) -> ValueSpec:
    return ValueSpec(
        cls.__name__,
        cls.__tm_doc__,
        cls.__dict__.get("default"),
        cls.__tm_kind__,
        f"{cls.__module__}.{cls.__qualname__}",
        cls.needs_packages,
    )
