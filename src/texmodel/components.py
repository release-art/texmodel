"""Components (M1): a `Command` is declared as a class; its fields are its arguments, its docstring its documentation.

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
    children = [Name, Fact * (2, 3), Slot * (0, 3)]     # `* "?"`, `* "*"`, `* "+"` are shorthands

pkg.document(CardBack(Name("Rex"), Fact("Friendly & loyal."), Fact("50% of $5")), options=["a4paper"])
```

`Text` fields are escaped on render (T3); a `Raw` field passes TeX through.

The body is TeX in `slot.tex` beside the class, or a short inline `body=`: `class Slot(Command, body="...")`.
Inside it `#text` is the argument named `text`; an environment has `card_back.begin.tex` and `card_back.end.tex`
(or `begin=` / `end=`). A bad declaration is refused when the class is defined.
"""

import dataclasses
import inspect
import sys
import types
import typing
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar, dataclass_transform

from ._internal.render import (
    Arg,
    EnvSpec,
    Spec,
    ValueSpec,
    arguments,
    check_name,
    snake,
)
from .errors import DeclarationError, Violation
from .types import CMYK, RGB, TEXT, Colour, Gray, Length, Raw

type Node = Command | Environment

_SHORT = {"?": (0, 1), "*": (0, None), "+": (1, None)}


@dataclasses.dataclass(frozen=True)
class Repeat:
    """How many of one component a grammar allows in a row (M4): `Fact * (2, 3)`, `Slot * "?"`, `Name` (exactly one)."""

    kind: type
    lo: int
    hi: int | None

    def __str__(self) -> str:
        count = (
            str(self.lo) if self.lo == self.hi else f"{self.lo} or more" if self.hi is None else f"{self.lo}-{self.hi}"
        )
        return f"{count} {self.kind.__name__}"


class _Meta(type):
    """Lets a component class be multiplied into a grammar term."""

    def __mul__(cls, count: int | tuple[int, int] | str) -> Repeat:
        bounds = _SHORT.get(count) if isinstance(count, str) else (count, count) if isinstance(count, int) else count
        if bounds is None or bounds[0] < 0 or (bounds[1] is not None and bounds[1] < bounds[0]):
            raise DeclarationError(
                f"{cls.__name__} * {count!r}: use n, (lo, hi), '?', '*' or '+'", code="TM-M020", path=cls.__name__
            )
        return Repeat(cls, *bounds)


def _document(cls: type) -> str:
    check_name(cls.__name__, "component")
    doc = (cls.__dict__.get("__doc__") or "").strip()
    if not doc:
        raise DeclarationError(f"{cls.__qualname__}: document the component in its docstring", code="TM-M002")
    return doc


def _prefix(cls: type) -> str:
    prefix: str | None = getattr(cls, "__tm_prefix__", None)
    if prefix is None:
        raise DeclarationError(
            f"{cls.__qualname__}: not registered with a package", code="TM-M019", hint="decorate it with @pkg.command"
        )
    return prefix


@dataclass_transform(frozen_default=True)
class Command(metaclass=_Meta):
    """A TeX command (`\\newcommand`) whose arguments are the class's fields."""

    __tm_inline__: ClassVar[str | None]
    __tm_unused__: ClassVar[tuple[str, ...]]
    __tm_args__: ClassVar[tuple[Arg, ...]]
    __tm_doc__: ClassVar[str]
    __tm_prefix__: ClassVar[str]  # set when a package registers the class

    def __init_subclass__(cls, *, body: str | None = None, unused: Sequence[str] = (), **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        doc = _document(cls)
        cls.__tm_inline__, cls.__tm_unused__, cls.__tm_doc__ = body, tuple(unused), doc
        # Optional fields are keyword-only (M2): mark them before the dataclass is built.
        for name in inspect.get_annotations(cls):
            if name in cls.__dict__ and not name.startswith("__"):
                setattr(cls, name, dataclasses.field(default=cls.__dict__[name], kw_only=True))
        dataclasses.dataclass(frozen=True, repr=False)(cls)
        cls.__doc__ = doc
        cls.__tm_args__ = _arguments(cls)

    def __repr__(self) -> str:
        return _repr(self)

    def validate(self) -> list[Violation]:
        """Every broken rule at once (E2), with its path into the tree."""
        return _violations(self, type(self).__name__)

    def render(self) -> str:
        """The call, `\\acFact{...}`: pure and deterministic (D2). Raises an `ExceptionGroup` if invalid."""
        return _render(self)


@dataclasses.dataclass(frozen=True, init=False, repr=False)
class Environment(metaclass=_Meta):
    """A TeX environment (`\\newenvironment`): fields are its arguments, positional arguments its children."""

    content: tuple[Node, ...]
    children: ClassVar[Sequence[type | Repeat]] = ()  # the grammar: components in order, with counts (M4)
    __tm_inline__: ClassVar[tuple[str | None, str | None]]
    __tm_unused__: ClassVar[tuple[str, ...]]
    __tm_args__: ClassVar[tuple[Arg, ...]]
    __tm_doc__: ClassVar[str]
    __tm_grammar__: ClassVar[tuple[Repeat, ...]]
    __tm_prefix__: ClassVar[str]

    def __init_subclass__(
        cls, *, begin: str | None = None, end: str | None = None, unused: Sequence[str] = (), **kwargs: Any
    ) -> None:
        super().__init_subclass__(**kwargs)
        cls.__tm_doc__ = doc = _document(cls)
        cls.__tm_inline__, cls.__tm_unused__ = (begin, end), tuple(unused)
        cls.__tm_grammar__ = _grammar(cls)
        for name in inspect.get_annotations(cls):
            if name in cls.__dict__ and not name.startswith("__"):
                setattr(cls, name, dataclasses.field(default=cls.__dict__[name], kw_only=True))
        dataclasses.dataclass(frozen=True, init=False, repr=False)(cls)
        cls.__doc__ = doc
        cls.__tm_args__ = _arguments(cls)

    def __init__(self, *content: Node, **args: str | Raw | None) -> None:
        fields = {f.name: f for f in dataclasses.fields(self) if f.name != "content"}
        if unknown := sorted(set(args) - set(fields)):
            raise TypeError(f"{type(self).__name__}() got unexpected keyword arguments {unknown}")
        if missing := sorted(n for n, f in fields.items() if f.default is dataclasses.MISSING and n not in args):
            raise TypeError(f"{type(self).__name__}() missing keyword arguments {missing}")
        object.__setattr__(self, "content", content)
        for name, f in fields.items():
            object.__setattr__(self, name, args.get(name, f.default))

    def __repr__(self) -> str:
        return _repr(self)

    def validate(self) -> list[Violation]:
        """Every broken rule at once (E2): argument types, and the children against the grammar (M4)."""
        return _violations(self, type(self).__name__)

    def render(self) -> str:
        """`\\begin{acCardBack}`, the children, `\\end{acCardBack}`. Raises an `ExceptionGroup` if invalid."""
        return _render(self)


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
                f"{cls.__qualname__}.{f.name}: unsupported type {hints[f.name]!r}; use Text, Raw or either | None",
                code="TM-M004",
                path=f"{cls.__name__}.{f.name}",
            )
        args.append(Arg(f.name, optional=f.default is not dataclasses.MISSING, raw=kind == "raw"))
    if sum(a.optional for a in args) > 1:
        raise DeclarationError(
            f"{cls.__qualname__}: more than one optional argument (TeX's \\newcommand allows one)",
            code="TM-M003",
            path=cls.__name__,
        )
    return tuple(args)


def _kind(hint: Any) -> str | None:
    """`"text"` for `Text` / `Text | None`, `"raw"` for `Raw` / `Raw | None`, else `None`."""
    members = [
        m for m in (typing.get_args(hint) if isinstance(hint, types.UnionType) else (hint,)) if m is not type(None)
    ]
    if members and all(typing.get_origin(m) is typing.Annotated and TEXT in typing.get_args(m)[1:] for m in members):
        return "text"
    return "raw" if members and all(m is Raw for m in members) else None


def _violations(node: Node, path: str) -> list[Violation]:
    cls = type(node)
    out: list[Violation] = []
    for a in cls.__tm_args__:
        v = getattr(node, a.name)
        if not (v is None and a.optional or isinstance(v, Raw if a.raw else str)):
            want = "Raw" if a.raw else "Text"
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


def _find(cls: type, inline: str | None, filename: str, option: str) -> tuple[str, str]:
    """A body is inline or a file beside the class, never both and never neither (M8)."""
    candidate = Path(sys.modules[cls.__module__].__file__ or ".").parent / filename
    qualname = f"{cls.__module__}.{cls.__qualname__}"
    if inline is not None and candidate.is_file():
        raise DeclarationError(
            f"{qualname}: has both an inline {option} and {filename}; keep one", code="TM-M005", path=cls.__name__
        )
    if inline is not None:
        return inline, "inline"
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8"), filename
    raise DeclarationError(
        f"{qualname}: no {option}; write {candidate} or pass {option}='...'", code="TM-M006", path=cls.__name__
    )


def spec_of(cls: type[Command]) -> Spec:
    """The declaration as the renderer sees it, with the body found (inline, or `<snake_name>.tex` beside the class)."""
    body, origin = _find(cls, cls.__tm_inline__, f"{snake(cls.__name__)}.tex", "body")
    return Spec(
        cls.__name__,
        cls.__tm_doc__,
        cls.__tm_args__,
        body,
        origin,
        f"{cls.__module__}.{cls.__qualname__}",
        cls.__tm_unused__,
    )


def env_spec_of(cls: type[Environment]) -> EnvSpec:
    """As `spec_of`, with two bodies: `<snake_name>.begin.tex` and `<snake_name>.end.tex`."""
    stem = snake(cls.__name__)
    begin, begin_origin = _find(cls, cls.__tm_inline__[0], f"{stem}.begin.tex", "begin")
    end, end_origin = _find(cls, cls.__tm_inline__[1], f"{stem}.end.tex", "end")
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


_KINDS = {Length: "Length", Colour: "Colour", bool: "Bool"}  # the closed set `Value[T]` accepts (T2)


class Value[T]:
    """A typed setting: `\\newlength`, `\\definecolor` or `\\newif`, chosen by `T`; `default` is an instance of `T`."""

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
        if arg not in _KINDS:
            raise DeclarationError(
                f"{cls.__qualname__}: base must be Value[Length], Value[Colour] or Value[Bool], not {arg!r}",
                code="TM-M012",
                path=cls.__name__,
            )
        if "default" not in cls.__dict__:
            raise DeclarationError(f"{cls.__qualname__}: no default", code="TM-M013", path=cls.__name__)
        default = cls.__dict__["default"]
        if not isinstance(default, arg):
            raise DeclarationError(
                f"{cls.__qualname__}: default {default!r} is not a {_KINDS[arg]}", code="TM-M014", path=cls.__name__
            )
        implied = ("xcolor",) if isinstance(default, (CMYK, RGB, Gray)) else ()
        cls.__tm_doc__, cls.__tm_kind__, cls.__tm_type__ = doc, _KINDS[arg], arg
        cls.needs_packages = tuple(sorted({*cls.needs_packages, *implied}))


def value_spec_of(cls: type[Value[Length] | Value[Colour] | Value[bool]]) -> ValueSpec:
    return ValueSpec(
        cls.__name__,
        cls.__tm_doc__,
        cls.__dict__["default"],
        cls.__tm_kind__,
        f"{cls.__module__}.{cls.__qualname__}",
        cls.needs_packages,
    )
