"""Commands and environments: frozen dataclasses whose fields are their arguments."""

import annotationlib
import dataclasses
import inspect
import types
import typing
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Self, dataclass_transform

import pydantic

from .._internal.emit import NodeKind
from .._internal.fields import KEYWORD, NOTES, OPTIONS, FieldNotes, field_spec
from .._internal.fieldtypes import RAW_TYPE, ChoiceType, ColourNameType
from .._internal.hints import type_of
from .._internal.pieces import pieces_of, template_text
from .._internal.render import (
    Arg,
    tex_arguments,
)
from ..body import (
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
)
from ..errors import DeclarationError, Violation
from ..interface import (
    BRACE,
    SQUARE,
    ArgOptions,
    Gap,
    arg,
)
from ..types import Choice, Raw

if TYPE_CHECKING:
    pass

from ._terms import Anywhere, Repeat, Times
from ._values import colour_named, document_of
from ._violations import render_of, violations_of

type Node = Command | Environment | Passthrough | Comment


Resolved = TexRaw | Ref | Comment | Group | Seq | Cs | Lit | Hole
Source = tuple[tuple[Resolved, ...], str]  # a body's pieces and where they came from

_TEX_NAMES = ("body", "begin", "end")


class _Times:
    """`Fact.times(2, 3)`: every component class has `.times`, so a grammar term reads as the count it allows."""

    def __get__(self, instance: object, owner: type) -> Times:
        return Times(owner)


def _required(f: "dataclasses.Field[Any]") -> bool:
    return f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING


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


class _Node:
    """What a `Command` and an `Environment` share: a frozen dataclass (its fields are the arguments), declaration
    data, `repr`, `violations` and `render`. It is not validated when built (`violations()` checks it, E2); data is
    read by `texmodel.spec`, which builds a model from the class's arguments."""

    __tm_abstract__: ClassVar[
        bool
    ]  # a shared base (`abstract=True`): fields and a body for subclasses, never registered
    __tm_unused__: ClassVar[tuple[str, ...]]
    __tm_tex__: ClassVar[dict[str, Any]]  # the class's own `body`, `begin` and `end`: TeX, not attributes
    __tm_kw_only__: ClassVar[bool] = (
        True  # fields are passed by keyword; `kw_only=False` on a class lets them be positional
    )
    __tm_fields__: ClassVar[tuple["dataclasses.Field[Any]", ...]]
    __tm_positional__: ClassVar[tuple[str, ...]]  # the fields a call may pass by position, in order
    __tm_args__: ClassVar[tuple[Arg, ...]]
    __tm_doc__: ClassVar[str]
    __tm_node__: ClassVar[NodeKind]  # what `emit` writes for it
    __tm_prefix__: ClassVar[str]  # set when a package registers the class
    __tm_cs__: ClassVar[str]  # likewise: the control sequence, see `control_name`
    __tm_given__: frozenset[str]  # the fields the caller passed
    cs: ClassVar[str | None] = None  # the TeX name, when it is not prefix + class name (`cs = "includegraphics"`)
    syntax: ClassVar[Syntax] = Syntax.LATEX2E  # the names `cs` may have: `Syntax.EXPL3` allows `_` and `:`
    defined_by: ClassVar[Library | None] = None  # the library block that defines it, so it renders no definition
    __tm_package__: ClassVar[object]  # the `Package` it was registered with
    read_with: ClassVar[tuple[type, ...]] = ()  # components `read_edits` reads whenever it reads this one (its holders)
    meta: ClassVar[
        Mapping[str, object]
    ] = {}  # the schema's `x-` keys on this component (`meta = {"audience": "deck"}`)
    times: ClassVar[Times] = _Times()  # pyright: ignore[reportAssignmentType]  # a descriptor: the class's term

    def __init_subclass__(cls, *, abstract: bool = False, kw_only: bool | None = None, **kwargs: Any) -> None:
        """Read what the class declares: its TeX, then its fields. `abstract` is a shared base and `kw_only=False` lets
        the required fields be passed by position (D1)."""
        super().__init_subclass__(**kwargs)
        own = annotationlib.get_annotations(cls, format=annotationlib.Format.FORWARDREF)
        reserved = {n for k in cls.__mro__[1:] if k.__module__ == __name__ for n in vars(k)} | set(
            dir(pydantic.BaseModel)
        )
        fields = [n for n, t in inspect.get_annotations(cls).items() if typing.get_origin(t) is not ClassVar]
        if clash := sorted(n for n in fields if n in reserved):
            raise DeclarationError(
                f"{cls.__qualname__}.{clash[0]}: the name of an attribute every component has",
                code="TM-M045",
                path=f"{cls.__name__}.{clash[0]}",
                hint="call the field something else (a component's data is a pydantic model: no `json`, `dict`...)",
            )
        # `body`, `begin` and `end` are TeX, not attributes; an annotated one is a field.
        cls.__tm_tex__ = {k: cls.__dict__[k] for k in _TEX_NAMES if k in cls.__dict__ and k not in own}
        for k in cls.__tm_tex__:
            delattr(cls, k)
        cls.__tm_abstract__ = abstract
        cls.__tm_kw_only__ = cls.__tm_kw_only__ if kw_only is None else kw_only
        doc = cls.__dict__.get("__doc__")
        dataclasses.dataclass(cls, frozen=True, init=False, repr=False, kw_only=True)
        cls.__doc__ = doc  # the dataclass writes a signature there when there is none
        cls.__tm_fields__ = dataclasses.fields(typing.cast("Any", cls))
        cls.__tm_positional__ = (
            ()
            if cls.__tm_kw_only__
            else tuple(f.name for f in cls.__tm_fields__ if _required(f) and not f.metadata.get(KEYWORD))
        )
        cls._prepare()

    @classmethod
    def _prepare(cls) -> None:
        """A family of components derives TeX or a grammar from its fields here: the fields are known, the TeX is not
        yet read."""

    def __init__(self, *positional: object, **given: object) -> None:
        """The node, not validated; an environment's positional arguments are its children, a command's are its
        required fields when the class says `kw_only=False`."""
        cls = type(self)
        environment = issubclass(cls, Environment)
        known = {f.name for f in cls.__tm_fields__}
        if unknown := sorted(set(given) - (known - {"content"} if environment else known)):
            raise TypeError(f"{cls.__name__}() got unexpected keyword arguments {unknown}")
        if environment:
            given = {**given, "content": positional}
        else:
            names = cls.__tm_positional__
            if len(positional) > len(names):
                raise TypeError(
                    f"{cls.__name__}() takes {len(names)} positional argument(s), got {len(positional)}"
                    + (
                        " (pass fields by keyword, or declare the class with kw_only=False)"
                        if cls.__tm_kw_only__
                        else ""
                    )
                )
            if twice := sorted(set(names[: len(positional)]) & set(given)):
                raise TypeError(f"{cls.__name__}() got multiple values for {twice}")
            given = dict(zip(names, positional, strict=False)) | given
        if missing := sorted(f.name for f in cls.__tm_fields__ if _required(f) and f.name not in given):
            raise TypeError(f"{cls.__name__}() missing arguments {missing}")
        for a in cls.__tm_args__:  # a colour value class given for a colour name is that name
            if isinstance(a.type, ColourNameType) and a.name in given:
                given[a.name] = colour_named(given[a.name])
        for f in cls.__tm_fields__:
            object.__setattr__(self, f.name, given[f.name] if f.name in given else f.default)
        object.__setattr__(self, "__tm_given__", frozenset(given))

    @property
    def fields_set(self) -> frozenset[str]:
        """The fields the caller passed, as given (`to_dict` writes these)."""
        return self.__tm_given__

    def copy(self, **update: object) -> Self:
        """The node with `update` for some fields; the fields set are the caller's and these."""
        kept = {n: getattr(self, n) for n in self.__tm_given__} | update
        children = kept.pop("content", ()) if isinstance(self, Environment) else ()
        return typing.cast("Any", type(self))(*children, **kept)

    def __repr__(self) -> str:
        return _repr(self)  # pyright: ignore[reportArgumentType]

    def __str__(self) -> str:
        return repr(self)

    def violations(self) -> list[Violation]:
        """Every broken rule at once (E2), with its path into the tree: argument types and, for an environment, the
        children against the grammar (M4)."""
        return violations_of(self, type(self).__name__)  # pyright: ignore[reportArgumentType]

    def render(self) -> str:
        """The TeX for this node (`\\acFact{...}`, or `\\begin{acCardBack}` ... `\\end{acCardBack}`): pure and
        deterministic (D2). Raises an `ExceptionGroup` if the node is invalid."""
        return render_of(self)  # pyright: ignore[reportArgumentType]


def _build(cls: type[_Node], unused: Sequence[str]) -> None:
    """Read a declared class once its fields are known. An abstract base needs no name a control word could have and
    no docstring: it is never registered."""
    cls.__tm_doc__ = doc = "" if cls.__tm_abstract__ else document_of(cls)
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
    return field_spec(default, FieldNotes(renamed_from, doc, dict(meta or {})))


@dataclass_transform(frozen_default=True, kw_only_default=True, field_specifiers=(field, arg))
class Command(_Node):
    """A TeX command (`\\newcommand`) whose arguments are the class's fields."""

    __tm_node__ = NodeKind.COMMAND
    __tm_inline__: ClassVar[Source | None]

    def __init_subclass__(cls, *, unused: Sequence[str] = (), **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.__tm_inline__ = _source(cls, "body")
        _build(cls, unused)

    @classmethod
    def call(cls, *required: ArgValue, **optional: ArgValue) -> Ref:
        """A body piece that calls this command: the required arguments positionally, the optional one by
        keyword, each a `Hole` (an argument of the component being defined), a `Raw`, a `str` (escaped) or a `Choice`.
        """
        return _ref(cls, RefKind.CALL, required, optional)


class Environment(_Node):
    """A TeX environment (`\\newenvironment`): fields are its arguments, positional arguments its children."""

    __tm_node__ = NodeKind.ENVIRONMENT
    content: tuple[Node, ...]
    children: ClassVar[Sequence[type | Repeat | Anywhere]] = ()  # the grammar: components in order, with counts (M4)
    checks: ClassVar[Sequence[Callable[[Any, str], list[Violation]]]] = ()  # more checks of a node, given its path
    __tm_inline__: ClassVar[tuple[Source | None, Source | None]]
    __tm_grammar__: ClassVar[tuple[Repeat | Anywhere, ...]]

    if TYPE_CHECKING:

        def __init__(self, *content: Node, **args: object) -> None: ...

    def __init_subclass__(cls, *, unused: Sequence[str] = (), **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.__tm_inline__ = (_source(cls, "begin"), _source(cls, "end"))
        cls.__tm_grammar__ = _grammar(cls)
        _build(cls, unused)

    @classmethod
    def open(cls, **args: ArgValue) -> Ref:
        """A body piece that starts this environment, `\\begin{acBox}`, with its arguments by keyword."""
        return _ref(cls, RefKind.OPEN, (), args)

    @classmethod
    def close(cls) -> Ref:
        """A body piece that ends this environment, `\\end{acBox}`."""
        return _ref(cls, RefKind.CLOSE, (), {})


class Passthrough(_Node, kw_only=False):
    """TeX written as it is (B3): a layout `\\vspace` between components. It claims no control sequence; a grammar must
    list it (`Passthrough.times.any()`, or `Anywhere(Passthrough)`) before an environment accepts one."""

    __tm_node__ = NodeKind.PASSTHROUGH
    tex: Raw
    __tm_args__: ClassVar[tuple[Arg, ...]] = (Arg("tex", RAW_TYPE, hint=Raw),)
    __tm_doc__: ClassVar[str] = "TeX written as it is."

    if TYPE_CHECKING:

        def __init__(self, tex: Raw) -> None: ...


def concrete_kinds(kind: type) -> list[type]:
    """A kind, or for an abstract base the registered classes under it (a package's own rows of a table)."""
    if not getattr(kind, "__tm_abstract__", False):
        return [kind]
    found: list[type] = []
    for sub in kind.__subclasses__():
        if getattr(sub, "__tm_abstract__", False):
            found += concrete_kinds(sub)
        elif hasattr(sub, "__tm_package__"):
            found.append(sub)
    return found


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
        if value is not None and not (isinstance(value, Hole) or _nested_ok(a, value) or a.type.ok(value)):
            problems.append(f"{a.name!r} must be a Hole or {a.type.describe()}")
    if problems and kind is not RefKind.CLOSE:
        raise DeclarationError(
            f"{cls.__name__}.{kind.value}(): " + "; ".join(problems),
            code="TM-M026",
            path=cls.__name__,
        )
    return Ref(cls, kind, tuple(values.get(a.name) for a in declared))


def _nested_ok(a: Arg, value: object) -> bool:
    """A `Raw` argument may hold calls (a `Ref`, or a `Seq` of pieces): a conditional's branch is TeX."""
    return a.type.nests_calls and isinstance(value, Ref | Seq)


def _repr(node: Command | Environment | Passthrough) -> str:
    """The constructor expression that rebuilds the node (D1): required fields positional only where the class allows
    it, optional ones by keyword."""
    shown = [repr(c) for c in node.content] if isinstance(node, Environment) else []
    required: list[str] = []
    optional: list[str] = []
    for a in type(node).__tm_args__:
        v = getattr(node, a.name)
        if a.optional and v is not None and v is not False:
            optional.append(f"{a.name}={v!r}")
        elif not a.optional and not isinstance(node, Environment):
            required.append(repr(v) if not type(node).__tm_kw_only__ else f"{a.name}={v!r}")
    return f"{type(node).__name__}({', '.join([*shown, *required, *optional])})"


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
    for f in cls.__tm_fields__:
        name = f.name
        if name == "content" and issubclass(cls, Environment):
            continue
        if name == "type":
            raise _reserved_type(cls)
        held = type_of(hints[name])
        if held is None:
            raise DeclarationError(
                f"{cls.__qualname__}.{name}: unsupported type {hints[name]!r}; "
                "use Text, PdfString, ColourName, Raw, Length, a colour model, int, bool, a Choice, a KeyVals, "
                "a tuple or list of those, or Star; any of them | None",
                code="TM-M004",
                path=f"{cls.__name__}.{name}",
            )
        if isinstance(held, ChoiceType):
            _choice(cls, name, held.choice)
        options: ArgOptions | None = f.metadata.get(OPTIONS)
        notes: FieldNotes = f.metadata.get(NOTES, FieldNotes())
        token = held.is_token
        if token and _required(f):
            raise DeclarationError(
                f"{cls.__qualname__}.{name}: a token is False unless given",
                code="TM-M039",
                path=f"{cls.__name__}.{name}",
                hint=f"write `{name}: Star = arg(default=False)`",
            )
        optional = token or not _required(f)
        delimiter = options.delimiter if options and options.delimiter else SQUARE if optional and not token else BRACE
        args.append(
            Arg(
                name,
                held,
                optional=optional,
                delimiter=delimiter,
                placed=options is not None or token,
                fill=options.fill if options else Gap.UNDECLARED,
                sep=(options.sep if options else None) or ",",
                group=options.group if options else None,
                booleans=(options.booleans if options else None) or ("true", "false"),
                renamed_from=notes.renamed_from,
                hint=hints[name],
                default=None if _required(f) else f.default,
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
