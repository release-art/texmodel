r"""Components (M1): a `Command` is declared as a class; its fields are its arguments, its docstring its documentation.

```python
pkg = Package("acme-cards", prefix="ac")

@pkg.command
class Slot(Command):
    '''A labelled paragraph; the label prints as its heading.'''
    text: Text
    label: Text | None = None      # optional: keyword-only, rendered as TeX's one optional argument
```

An optional field's `Text`, `Raw`, number, flag or `Choice` default is TeX's too: `label: Text | None = "Note"` is
`\newcommand{\acSlot}[2][Note]{...}`; with no default it is `[]`.

`field(doc=..., meta={...})` and a class-level `meta = {...}` put a description and `x-` keys in the JSON Schema.

A `Value[T]` is a typed setting; its `default` is an instance of `T` and its type decides the TeX (M1a, T4, T5):

```python
@pkg.value
class FactGap(Value[Length]):
    '''Space under each fact.'''
    default = Length("2mm")
```

A `Value[Length]` may leave `default` out (a bare `\newlength`, set later); a `Value[Colour]` may rename itself
(`colour_name = "acInk"`). A package adds its own kinds with a `ValueKind` (`texmodel.types`): what it holds, the names
it claims, the TeX that declares and sets it, the packages it needs (a name, or a `Package` of this project). `Toggle`
in `texmodel.std.etoolbox` is one, built from etoolbox's own bindings:

```python
@pkg.value
class Draft(Value[Toggle]):
    '''Print the draft banner.'''
    default = False          # \newtoggle{acDraft} \togglefalse{acDraft}
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

pkg.document(CardBack(Name("Rex"), Fact("Friendly & loyal."), Fact("50% of $5")))
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

import annotationlib
import dataclasses
import inspect
import types
import typing
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal, dataclass_transform, overload

import pydantic
from pydantic.fields import FieldInfo
from pydantic_core import CoreSchema, core_schema

from ._internal.pieces import pieces_of, refs_in, syntaxes_in, template_text
from ._internal.render import (
    BOOL,
    COLOUR,
    LENGTH,
    RAW_KIND,
    TEXT_KIND,
    Arg,
    EnvSpec,
    Spec,
    ValueSpec,
    argument_violations,
    arguments,
    call_arguments,
    check_name,
    tex_arguments,
    written,
)
from ._internal.values import value_ok
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
    inline_text,
    join,
)
from .errors import DeclarationError, Violation
from .interface import BRACE, RAW_BODY, SQUARE, ArgOptions, BodyKind, FieldNotes, Gap, arg, body_of, field_info
from .types import TEXT, Choice, Colour, Length, Raw, Text, ValueKind

if TYPE_CHECKING:
    from .package import Package

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


class _Meta(type(pydantic.BaseModel)):
    """Gives every component class `.times`, so a grammar term reads `Fact.times(2, 3)`, and builds a node from
    positional arguments: a command's go to its required fields in order, an environment's are its children (D1)."""

    def __new__(mcs, name: str, bases: tuple[type, ...], namespace: dict[str, Any], **kwargs: Any) -> type:  # noqa: N804
        """A class's `body`, `begin` and `end` are TeX, not fields: `_source` reads them from `__tm_tex__`, which
        pydantic does not see. An annotated one is a field."""
        annotate = annotationlib.get_annotate_from_class_namespace(namespace)
        annotated = {
            *namespace.get("__annotations__", {}),
            *(annotationlib.call_annotate_function(annotate, annotationlib.Format.FORWARDREF) if annotate else {}),
        }
        namespace["__tm_tex__"] = {
            k: namespace.pop(k) for k in ("body", "begin", "end") if k in namespace and k not in annotated
        }
        return super().__new__(mcs, name, bases, namespace, **kwargs)

    @property
    def times(cls) -> _Times:
        return _Times(cls)

    def __call__(cls, *positional: object, **given: object):  # noqa: ANN204  # unannotated: a type checker reads __init__
        """The node, not validated (`violations()` checks it, E2); `model_fields_set` is what was passed."""
        node = typing.cast("type[_Node]", cls)
        fields = node.model_fields
        environment = issubclass(node, Environment)
        if unknown := sorted(set(given) - (set(fields) - {"content"} if environment else set(fields))):
            raise TypeError(f"{cls.__name__}() got unexpected keyword arguments {unknown}")
        if environment:
            given = {**given, "content": positional}
        else:
            # A required field is positional, as a dataclass's; one with a default, or written `arg()`, is keyword-only.
            names = [n for n, f in fields.items() if f.kw_only is False or (f.kw_only is None and f.is_required())]
            if len(positional) > len(names):
                raise TypeError(f"{cls.__name__}() takes {len(names)} positional argument(s), got {len(positional)}")
            if twice := sorted(set(names[: len(positional)]) & set(given)):
                raise TypeError(f"{cls.__name__}() got multiple values for {twice}")
            given = dict(zip(names, positional, strict=False)) | given
        if missing := sorted(n for n, f in fields.items() if f.is_required() and n not in given):
            raise TypeError(f"{cls.__name__}() missing arguments {missing}")
        return node.model_construct(set(given), **given)


def _document(cls: type) -> str:
    """The docstring of a component, which must be documented and named as a TeX control word would be."""
    check_name(cls.__name__, "component")
    doc = (cls.__dict__.get("__doc__") or "").strip()
    if not doc:
        raise DeclarationError(f"{cls.__qualname__}: document the component in its docstring", code="TM-M002")
    return doc


def _source(cls: type, name: str) -> Source | None:
    """The class's `body` / `begin` / `end` as (pieces, origin), or None: its own, else the nearest base class's (a
    shared base is declared `abstract=True`).

    It is a string, a `TemplateRef` (the file is read now, relative to the module that wrote it), a `TexRaw`, a `Ref`,
    a `Comment`, a sequence, iterator or generator of those, or a method returning any of them. A field of that name
    is not a body.
    """
    owner = next((k for k in cls.__mro__ if name in k.__dict__.get("__tm_tex__", {})), None)
    if owner is None:
        return None
    found: object = owner.__dict__["__tm_tex__"][name]
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
            text = template_text(piece, owner.__module__, f"{cls.__qualname__}.{name}")
            out.append(TexRaw(text, piece.whitespace, piece.syntax))
            origins.append(piece.path.name)
        else:
            out.append(TexRaw(piece) if isinstance(piece, str) else piece)
            origins.append("inline")
    return tuple(out), " + ".join(dict.fromkeys(origins))


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


class _Node(pydantic.BaseModel, metaclass=_Meta):
    """What a `Command` and an `Environment` share: a frozen pydantic model (its fields are the arguments), declaration
    data, `repr`, `violations` and `render`. The schema is built on first use (`from_dict`, `to_dict`, a schema)."""

    model_config = pydantic.ConfigDict(frozen=True, defer_build=True)

    __tm_abstract__: ClassVar[
        bool
    ]  # a shared base (`abstract=True`): fields and a body for subclasses, never registered
    __tm_unused__: ClassVar[tuple[str, ...]]
    __tm_args__: ClassVar[tuple[Arg, ...]]
    __tm_doc__: ClassVar[str]
    __tm_prefix__: ClassVar[str]  # set when a package registers the class
    __tm_cs__: ClassVar[str]  # likewise: the control sequence, see `control_name`
    cs: ClassVar[str | None] = None  # the TeX name, when it is not prefix + class name (`cs = "includegraphics"`)
    syntax: ClassVar[Syntax] = Syntax.LATEX2E  # the names `cs` may have: `Syntax.EXPL3` allows `_` and `:`
    defined_by: ClassVar[Library | None] = None  # the library block that defines it, so it renders no definition
    __tm_package__: ClassVar[object]  # the `Package` it was registered with
    meta: ClassVar[
        Mapping[str, object]
    ] = {}  # the schema's `x-` keys on this component (`meta = {"audience": "deck"}`)

    def __init_subclass__(cls, *, unused: Sequence[str] = (), abstract: bool = False, **kwargs: Any) -> None:
        """`unused` and `abstract` are read by `__pydantic_init_subclass__`, once pydantic has the fields."""
        super().__init_subclass__(**kwargs)
        fields = [n for n, t in inspect.get_annotations(cls).items() if typing.get_origin(t) is not ClassVar]
        if clash := sorted(n for n in fields if n.startswith("model_") or hasattr(_Node, n)):
            raise DeclarationError(
                f"{cls.__qualname__}.{clash[0]}: the name of an attribute every component has",
                code="TM-M045",
                path=f"{cls.__name__}.{clash[0]}",
                hint="call the field something else (a component is a pydantic model: no `model_` prefix, no `copy`)",
            )

    @pydantic.model_validator(mode="before")
    @classmethod
    def _renamed(cls, data: object) -> object:
        """Data may name a field by its old name (`field(renamed_from=)`); both names given is an error."""
        old = {a.renamed_from: a.name for a in cls.__tm_args__ if a.renamed_from}
        if not old or not isinstance(data, Mapping):
            return data
        out = dict(typing.cast("Mapping[str, object]", data))
        for was, name in old.items():
            if was in out:
                if name in out:
                    raise ValueError(f"{name!r} and its old name {was!r} are both given")
                out[name] = out.pop(was)
        return out

    def __repr__(self) -> str:
        return _repr(self)  # pyright: ignore[reportArgumentType]

    def __str__(self) -> str:
        return repr(self)

    def violations(self) -> list[Violation]:
        """Every broken rule at once (E2), with its path into the tree: argument types and, for an environment, the
        children against the grammar (M4)."""
        return _violations(self, type(self).__name__)  # pyright: ignore[reportArgumentType]

    def render(self) -> str:
        """The TeX for this node (`\\acFact{...}`, or `\\begin{acCardBack}` ... `\\end{acCardBack}`): pure and
        deterministic (D2). Raises an `ExceptionGroup` if the node is invalid."""
        return _render(self)  # pyright: ignore[reportArgumentType]


def _build(cls: type[_Node], unused: Sequence[str], *, abstract: bool) -> None:
    """Read a declared class once pydantic has its fields. An abstract base needs no name a control word could have
    and no docstring: it is never registered."""
    cls.__tm_abstract__ = abstract
    cls.__tm_doc__ = doc = "" if abstract else _document(cls)
    cls.__tm_unused__ = tuple(unused)
    if "cs" in cls.__dict__:
        Cs(cls.__dict__["cs"], cls.syntax)  # a control word of the class's syntax (TM-M027)
    cls.__doc__ = doc
    cls.__tm_args__ = _arguments(cls)  # pyright: ignore[reportArgumentType]


def field(
    *,
    renamed_from: str | None = None,
    doc: str | None = None,
    meta: Mapping[str, object] | None = None,
    default: Any = dataclasses.MISSING,  # noqa: ANN401  # as dataclasses.field
) -> Any:  # noqa: ANN401
    """A field that data (`from_dict`) may still name `renamed_from`: `to_dict` and the schema use the field's name, the
    old key loads, and the schema records it as `x-renamed-from` (§21). `doc` is its description in the schema and
    `meta` its `x-` keys (`meta={"audience": "deck"}` is `x-audience`). `default` makes it optional, keyword-only."""
    return field_info(default, FieldNotes(renamed_from, doc, dict(meta or {})), kw_only=None)


@dataclass_transform(frozen_default=True, field_specifiers=(field, arg))
class Command(_Node):
    """A TeX command (`\\newcommand`) whose arguments are the class's fields."""

    __tm_inline__: ClassVar[Source | None]

    @classmethod
    def __pydantic_init_subclass__(cls, *, unused: Sequence[str] = (), abstract: bool = False, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        cls.__tm_inline__ = _source(cls, "body")
        _build(cls, unused, abstract=abstract)

    @classmethod
    def call(cls, *required: ArgValue, **optional: ArgValue) -> Ref:
        """A body piece that calls this command: the required arguments positionally, the optional one by
        keyword, each a `Hole` (an argument of the component being defined), a `Raw`, a `str` (escaped) or a `Choice`.
        """
        return _ref(cls, RefKind.CALL, required, optional)


class Environment(_Node):
    """A TeX environment (`\\newenvironment`): fields are its arguments, positional arguments its children."""

    content: tuple[Node, ...]
    children: ClassVar[Sequence[type | Repeat | Anywhere]] = ()  # the grammar: components in order, with counts (M4)
    __tm_inline__: ClassVar[tuple[Source | None, Source | None]]
    __tm_grammar__: ClassVar[tuple[Repeat | Anywhere, ...]]

    if TYPE_CHECKING:  # at run time the metaclass builds the node (`_Meta.__call__`)

        def __init__(self, *content: Node, **args: object) -> None: ...

    @classmethod
    def __pydantic_init_subclass__(cls, *, unused: Sequence[str] = (), abstract: bool = False, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        cls.__tm_inline__ = (_source(cls, "begin"), _source(cls, "end"))
        cls.__tm_grammar__ = _grammar(cls)
        _build(cls, unused, abstract=abstract)
        # Data's children are this grammar's components and the package's comments: the schema is built on first use.
        cls.__pydantic_fields__["content"] = FieldInfo.from_annotation(tuple[Annotated[Node, Children(cls)], ...])

    @classmethod
    def open(cls, **args: ArgValue) -> Ref:
        """A body piece that starts this environment, `\\begin{acBox}`, with its arguments by keyword."""
        return _ref(cls, RefKind.OPEN, (), args)

    @classmethod
    def close(cls) -> Ref:
        """A body piece that ends this environment, `\\end{acBox}`."""
        return _ref(cls, RefKind.CLOSE, (), {})


class Passthrough(_Node):
    """TeX written as it is (B3): a layout `\\vspace` between components. It claims no control sequence; a grammar must
    list it (`Passthrough.times.any()`, or `Anywhere(Passthrough)`) before an environment accepts one."""

    tex: Raw
    __tm_args__: ClassVar[tuple[Arg, ...]] = (Arg("tex", RAW_BODY, hint=Raw),)
    __tm_doc__: ClassVar[str] = "TeX written as it is."

    if TYPE_CHECKING:  # at run time the metaclass builds the node (`_Meta.__call__`)

        def __init__(self, tex: Raw) -> None: ...


def _tag(value: object) -> object:
    """A child's component in data (`"type"`), or the class name of a node given as it is."""
    return value.get("type") if isinstance(value, Mapping) else type(value).__name__  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]


_COMMENT_MODELS: dict[type[Comment], type[pydantic.BaseModel]] = {}


def _comment_model(kind: type[Comment]) -> type[pydantic.BaseModel]:
    """A comment's fields as a model, for data and the schema (a `Comment` is not a pydantic model)."""
    if kind not in _COMMENT_MODELS:
        fields: dict[str, Any] = dict.fromkeys(kind.__tm_fields__, (str, ...))
        _COMMENT_MODELS[kind] = pydantic.create_model(kind.__name__, __doc__=kind.__doc__, **fields)
    return _COMMENT_MODELS[kind]


def _comment_fields(comment: Comment) -> dict[str, str]:
    return {f: getattr(comment, f) for f in comment.__tm_fields__}


@dataclasses.dataclass(frozen=True)
class Children:
    """The schema of a list of nodes in data: a union, told apart by `"type"`, of the components an environment's
    grammar names, or (given a package) of every command and environment it registers and `Passthrough`; and `Comment`
    and the package's comment classes. Plumbing for `spec`."""

    owner: "type[Environment] | Package"

    def __get_pydantic_core_schema__(self, source: object, handler: pydantic.GetCoreSchemaHandler) -> CoreSchema:
        if isinstance(self.owner, type):
            package = typing.cast("Package | None", getattr(self.owner, "__tm_package__", None))
            kinds = [t.kind for t in self.owner.__tm_grammar__]
        else:
            package = self.owner
            kinds = [c for c in package.registered if issubclass(c, Command | Environment)] + [Passthrough]
        choices: dict[Any, CoreSchema] = {kind.__name__: handler.generate_schema(kind) for kind in kinds}
        for kind in (Comment, *(package.comments if package else ())):
            choices[kind.__name__] = core_schema.no_info_after_validator_function(
                lambda model, kind=kind: kind(**dict(model)),
                handler.generate_schema(_comment_model(kind)),
                serialization=core_schema.plain_serializer_function_ser_schema(_comment_fields),
            )
        return core_schema.tagged_union_schema(choices, discriminator=_tag)


type ArgValue = object  # a Hole, or a value of the argument's type


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
        if value is not None and not (isinstance(value, Hole) or _nested_ok(a, value) or value_ok(a.body, value)):
            problems.append(f"{a.name!r} must be a Hole or {a.body.describe()}")
    if problems and kind is not RefKind.CLOSE:
        raise DeclarationError(
            f"{cls.__name__}.{kind.value}(): " + "; ".join(problems),
            code="TM-M026",
            path=cls.__name__,
        )
    return Ref(cls, kind, tuple(values.get(a.name) for a in declared))


def _nested_ok(a: Arg, value: object) -> bool:
    """A `Raw` argument may hold calls (a `Ref`, or a `Seq` of pieces): a conditional's branch is TeX."""
    return a.body.kind is BodyKind.RAW and a.body.expression is None and isinstance(value, Ref | Seq)


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


def _repr(node: Command | Environment | Passthrough) -> str:
    """The constructor expression that rebuilds the node (D1): required fields positional, optional ones by keyword."""
    shown = [repr(c) for c in node.content] if isinstance(node, Environment) else []
    keywords: list[str] = []
    for a in type(node).__tm_args__:
        v = getattr(node, a.name)
        if a.optional and v is not None and v is not False:
            keywords.append(f"{a.name}={v!r}")
        elif not a.optional and not isinstance(node, Environment):
            shown.append(repr(v))
    shown += keywords
    return f"{type(node).__name__}({', '.join(shown)})"


def _grammar(cls: type[Environment]) -> tuple[Repeat | Anywhere, ...]:
    terms: list[Repeat | Anywhere] = []
    for item in cls.children:  # inherited from a shared base, or its own
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
    for name, f in cls.model_fields.items():
        if name == "content" and issubclass(cls, Environment):
            continue
        if name == "type":
            raise _reserved_type(cls)
        body = body_of(hints[name])
        if body is None:
            raise DeclarationError(
                f"{cls.__qualname__}.{name}: unsupported type {hints[name]!r}; "
                "use Text, PdfString, ColourName, Raw, Length, a colour model, int, bool, a Choice, a KeyVals, "
                "a tuple or list of those, or Star; any of them | None",
                code="TM-M004",
                path=f"{cls.__name__}.{name}",
            )
        if body.choice is not None:
            _choice(cls, name, body.choice)
        options = next((m for m in f.metadata if isinstance(m, ArgOptions)), None)
        notes = next((m for m in f.metadata if isinstance(m, FieldNotes)), FieldNotes())
        token = body.kind is BodyKind.TOKEN
        if token and f.is_required():
            raise DeclarationError(
                f"{cls.__qualname__}.{name}: a token is False unless given",
                code="TM-M039",
                path=f"{cls.__name__}.{name}",
                hint=f"write `{name}: Star = arg(default=False)`",
            )
        optional = token or not f.is_required()
        delimiter = options.delimiter if options and options.delimiter else SQUARE if optional and not token else BRACE
        args.append(
            Arg(
                name,
                body,
                optional=optional,
                delimiter=delimiter,
                placed=options is not None or token,
                fill=options.fill if options else Gap.UNDECLARED,
                sep=(options.sep if options else None) or ",",
                group=options.group if options else None,
                booleans=(options.booleans if options else None) or ("true", "false"),
                renamed_from=notes.renamed_from,
                hint=hints[name],
                default=None if f.is_required() else f.default,
                doc=notes.doc,
                meta=notes.meta,
            )
        )
    _check_signature(cls, tuple(args))
    return tuple(args)


def _check_signature(cls: type, args: tuple[Arg, ...]) -> None:
    """The declaration errors of a signature: a group member is optional, and an optional slot followed by
    another optional one says what is written, or that it is refused, when it is left out and the other is set."""
    for a in args:
        if a.group is not None and (not a.optional or a.token):
            raise DeclarationError(
                f"{cls.__qualname__}.{a.name}: a member of group {a.group.name!r} must be an optional field with a "
                "default",
                code="TM-M038",
                path=f"{cls.__name__}.{a.name}",
            )
    ordered = tex_arguments(args)
    for i, a in enumerate(ordered):
        if (
            a.optional
            and not a.token
            and a.fill is Gap.UNDECLARED
            and any(
                b.optional and not b.token and (a.group is None or b.group is not a.group) for b in ordered[i + 1 :]
            )
        ):
            raise DeclarationError(
                f"{cls.__qualname__}.{a.name}: an optional argument followed by another optional one must say what is "
                "written when it is left out and the other is set",
                code="TM-M037",
                path=f"{cls.__name__}.{a.name}",
                hint='declare it with arg(fill="") to write empty delimiters, or arg(fill=Gap.REFUSE) to refuse that',
            )


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


def _violations(node: Command | Environment | Passthrough, path: str) -> list[Violation]:
    cls = type(node)
    out: list[Violation] = []
    for a in cls.__tm_args__:
        if why := argument_violations(a, getattr(node, a.name)):
            out.append(Violation("TM-C003", f"{path}.{a.name}", f"{a.name}: {why}"))
    out += _slot_violations(node, path)
    if isinstance(node, Environment):
        out += _grammar_violations(node, path)
        for i, child in enumerate(node.content):
            if isinstance(child, Command | Environment | Passthrough):  # pyright: ignore[reportUnnecessaryIsInstance]
                out += _violations(child, f"{path}/{type(child).__name__}[{i}]")
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


def call_line(node: Command | Environment) -> tuple[str, tuple[tuple[str, int, int], ...]]:
    """The call of a command, or the `\\begin` line of an environment, and where each argument's text stands in it as
    `(field, start, end)` (delimiters excluded)."""
    cls = type(node)
    name = control_name(cls)
    args, spans = call_arguments(cls.__tm_args__, {a.name: getattr(node, a.name) for a in cls.__tm_args__})
    head = f"\\{name}" if isinstance(node, Command) else f"\\begin{{{name}}}"
    return head + args, tuple((arg, start + len(head), end + len(head)) for arg, start, end in spans)


def _emit(node: Node) -> str:
    if isinstance(node, Comment):
        return node.render()
    if isinstance(node, Passthrough):
        return node.tex.tex
    first = call_line(node)[0]
    if isinstance(node, Command):
        return first
    return "\n".join([first, *map(_emit, node.content), f"\\end{{{control_name(type(node))}}}"])


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


_KINDS: dict[object, ValueKind] = {Length: LENGTH, Colour: COLOUR, bool: BOOL, str: TEXT_KIND, Raw: RAW_KIND}


class Value[T]:
    """A typed setting: `\\newlength`, `\\definecolor`, `\\newif`, `\\newcommand` or a package's own (`Toggle`), chosen
    by `T`; `default` is an instance of `T`. A `Value[Text]` of an adopted package may leave `default` out: the
    hand-written package has it; so may a `Value[Length]` the package computes later. `colour_name` renames a colour."""

    default: T  # not ClassVar[T]: pyright refuses type variables in ClassVar; subclasses assign it in the class body
    needs_packages: ClassVar[tuple["str | Package", ...]] = ()  # data, not mutation: the package takes the union (M14)
    colour_name: ClassVar[str | None] = None  # a `Value[Colour]`'s name when it is not `<prefix>-<kebab>` (`"acInk"`)
    cs: ClassVar[str | None] = None  # the whole control sequence, when it is not prefix + class name (`"acshowcrop"`)
    defined_by: ClassVar[Library | None] = None  # the library block that defines it, so it renders no definition
    meta: ClassVar[Mapping[str, object]] = {}  # the schema's `x-` keys on this value
    __tm_doc__: ClassVar[str]
    __tm_kind__: ClassVar[ValueKind]
    __tm_prefix__: ClassVar[str]
    __tm_cs__: ClassVar[str]  # the control sequence, once registered (not for a colour); see `control_name`

    @classmethod
    def declared_default(cls) -> T | None:
        """The class's `default` (None when it has none): reading `default` through a class is ambiguous to a type
        checker, this is not."""
        return getattr(cls, "default", None)

    def __init__(self, value: T) -> None:
        """A document's setting for this value (D1a): `FactGap(Length("3mm"))`, checked against the declared type."""
        if not isinstance(value, kind := type(self).__tm_kind__.python):
            raise DeclarationError(f"{type(self).__name__}({value!r}): expected a {kind}", code="TM-M014")
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
        marks = typing.get_args(arg)[1:] if typing.get_origin(arg) is typing.Annotated else ()
        kind = next((m for m in marks if isinstance(m, ValueKind)), TEXT_KIND if TEXT in marks else _KINDS.get(arg))
        if kind is None:
            raise DeclarationError(
                f"{cls.__qualname__}: base must be Value of Length, Colour, Bool, Text or Raw, or of a package's own "
                f"kind (etoolbox's Toggle), not {arg!r}",
                code="TM-M012",
                path=cls.__name__,
            )
        defined = cls.defined_by is not None
        if "default" not in cls.__dict__ and not kind.may_omit and not defined:
            raise DeclarationError(f"{cls.__qualname__}: no default", code="TM-M013", path=cls.__name__)
        if defined and "default" in cls.__dict__:
            raise DeclarationError(
                f"{cls.__qualname__}: has a default, but a library block defines it",
                code="TM-M032",
                path=cls.__name__,
                hint="remove the default: the block is the definition",
            )
        if "cs" in cls.__dict__:
            if kind.named:
                raise DeclarationError(
                    f"{cls.__qualname__}: a colour is named with colour_name, not cs", code="TM-M012", path=cls.__name__
                )
            Cs(cls.__dict__["cs"], Syntax.LATEX2E)  # a control word (TM-M027)
        if cls.colour_name is not None and not kind.named:
            raise DeclarationError(
                f"{cls.__qualname__}: colour_name belongs to a Value[Colour]", code="TM-M012", path=cls.__name__
            )
        default = cls.__dict__.get("default")
        if default is not None and not isinstance(default, kind.python):
            raise DeclarationError(
                f"{cls.__qualname__}: default {default!r} is not a {kind.name}", code="TM-M014", path=cls.__name__
            )
        cls.__tm_doc__, cls.__tm_kind__ = doc, kind
        cls.needs_packages = tuple(
            sorted({*cls.needs_packages, *kind.needs}, key=lambda p: p if isinstance(p, str) else p.name)
        )


type AnyValue = Value[Length] | Value[Colour] | Value[bool] | Value[Text] | Value[Raw]


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


@dataclasses.dataclass(frozen=True)
class ArgumentInfo:
    """One argument of a registered command or environment."""

    name: str = dataclasses.field(metadata={"doc": "the field's name"})
    optional: bool = dataclasses.field(metadata={"doc": "it may be left out"})
    doc: str | None = dataclasses.field(metadata={"doc": "its `field(doc=)`, if it has one"})


@dataclasses.dataclass(frozen=True)
class Description:
    """What `describe` reports about a registered component or value."""

    category: Literal["command", "environment", "value"] = dataclasses.field(metadata={"doc": "what it is"})
    name: str = dataclasses.field(metadata={"doc": "the class name"})
    cs: str | None = dataclasses.field(
        metadata={"doc": "the control sequence without the backslash; None for a colour"}
    )
    doc: str = dataclasses.field(metadata={"doc": "the class's docstring"})
    arguments: tuple[ArgumentInfo, ...] = dataclasses.field(metadata={"doc": "in TeX order; empty for a value"})
    python: object | None = dataclasses.field(
        metadata={"doc": "a value's Python type (bool, Length, str, Raw, Colour); None otherwise"}
    )
    default: object | None = dataclasses.field(metadata={"doc": "a value's default; None otherwise"})
    colour_name: str | None = dataclasses.field(metadata={"doc": "a colour's name; None otherwise"})
    body: str | None = dataclasses.field(
        metadata={
            "doc": "a command's body or an environment's `begin`, with `#name` holes; None for a value or adopted"
        }
    )
    end: str | None = dataclasses.field(metadata={"doc": "an environment's `end`; None otherwise"})


def describe(cls: type) -> Description:
    """A registered command, environment or value class as data, so a program need not read its `__tm_*` attributes.
    An unregistered class is `TM-M019`."""
    if not hasattr(cls, "__tm_prefix__"):
        raise DeclarationError(
            f"{cls.__qualname__}: not registered with a package", code="TM-M019", hint="decorate it with @pkg.command"
        )
    if issubclass(cls, Value):
        kind: ValueKind = cls.__tm_kind__
        return Description(
            "value",
            cls.__name__,
            None if kind.named else cls.__tm_cs__,
            cls.__tm_doc__,
            (),
            kind.python,
            typing.cast("object | None", cls.declared_default()),
            cls.colour_name,
            None,
            None,
        )
    if not issubclass(cls, Command | Environment):
        raise DeclarationError(f"{cls.__qualname__}: not a command, environment or value", code="TM-M019")
    body = end = None
    if cls.defined_by is None and issubclass(cls, Command) and cls.__tm_inline__:
        body = spec_of(cls).body
    elif cls.defined_by is None and issubclass(cls, Environment) and cls.__tm_inline__[0]:
        spec = env_spec_of(cls)
        body, end = spec.begin, spec.end
    return Description(
        "command" if issubclass(cls, Command) else "environment",
        cls.__name__,
        cls.__tm_cs__,
        cls.__tm_doc__,
        tuple(ArgumentInfo(a.name, a.optional, a.doc) for a in cls.__tm_args__),
        None,
        None,
        None,
        body,
        end,
    )


__all__ = [
    "AnyValue",
    "Anywhere",
    "ArgValue",
    "ArgumentInfo",
    "Children",
    "Command",
    "Description",
    "Environment",
    "Node",
    "Passthrough",
    "Repeat",
    "Resolved",
    "Source",
    "Value",
    "control_name",
    "describe",
    "field",
]
