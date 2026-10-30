"""Commands, environments and the metaclass that builds a node."""

import annotationlib
import dataclasses
import inspect
import types
import typing
from collections.abc import (
    Callable,
    Mapping,
    Sequence,
)
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, dataclass_transform

import pydantic
from pydantic.fields import FieldInfo
from pydantic_core import CoreSchema, core_schema

from .._internal.bodies import body_of
from .._internal.emit import NodeKind
from .._internal.fields import FieldNotes, field_info
from .._internal.pieces import pieces_of, template_text
from .._internal.render import (
    Arg,
    tex_arguments,
)
from .._internal.values import value_ok
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
    RAW_BODY,
    SQUARE,
    ArgOptions,
    BodyKind,
    Gap,
    arg,
)
from ..types import Choice, Raw

if TYPE_CHECKING:
    from ..package import Package

from ._terms import Anywhere, Repeat, Times
from ._values import colour_named, document_of
from ._violations import render_of, violations_of

type Node = Command | Environment | Passthrough | Comment


Resolved = TexRaw | Ref | Comment | Group | Seq | Cs | Lit | Hole
Source = tuple[tuple[Resolved, ...], str]  # a body's pieces and where they came from


class _Meta(type(pydantic.BaseModel)):
    """Gives every component class `.times`, so a grammar term reads `Fact.times(2, 3)`, and builds a node: an
    environment's positional arguments are its children; its fields and a command's are keywords, unless a command's
    class says `kw_only=False` (then its required fields may be positional, in order) (D1)."""

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
    def times(cls) -> Times:
        return Times(cls)

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
            # Fields are keyword-only unless the class says `kw_only=False`; then a required field is positional, as a
            # dataclass's, and one with a default, or written `arg()`, stays keyword-only.
            names = (
                []
                if node.__tm_kw_only__
                else [n for n, f in fields.items() if f.kw_only is False or (f.kw_only is None and f.is_required())]
            )
            if len(positional) > len(names):
                raise TypeError(
                    f"{cls.__name__}() takes {len(names)} positional argument(s), got {len(positional)}"
                    + (
                        " (pass fields by keyword, or declare the class with kw_only=False)"
                        if node.__tm_kw_only__
                        else ""
                    )
                )
            if twice := sorted(set(names[: len(positional)]) & set(given)):
                raise TypeError(f"{cls.__name__}() got multiple values for {twice}")
            given = dict(zip(names, positional, strict=False)) | given
        if missing := sorted(n for n, f in fields.items() if f.is_required() and n not in given):
            raise TypeError(f"{cls.__name__}() missing arguments {missing}")
        for a in node.__tm_args__:  # a colour value class given for a colour name is that name
            if a.body.kind is BodyKind.COLOUR_NAME and a.name in given:
                given[a.name] = colour_named(given[a.name])
        return node.model_construct(set(given), **given)


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


class _Node(pydantic.BaseModel, metaclass=_Meta):
    """What a `Command` and an `Environment` share: a frozen pydantic model (its fields are the arguments), declaration
    data, `repr`, `violations` and `render`. The schema is built on first use (`from_dict`, `to_dict`, a schema)."""

    model_config = pydantic.ConfigDict(frozen=True, defer_build=True)

    __tm_abstract__: ClassVar[
        bool
    ]  # a shared base (`abstract=True`): fields and a body for subclasses, never registered
    __tm_unused__: ClassVar[tuple[str, ...]]
    __tm_tex__: ClassVar[dict[str, Any]]  # the class's own `body`, `begin` and `end`, read from the namespace
    __tm_kw_only__: ClassVar[bool] = (
        True  # fields are passed by keyword; `kw_only=False` on a class lets them be positional
    )
    __tm_args__: ClassVar[tuple[Arg, ...]]
    __tm_doc__: ClassVar[str]
    __tm_node__: ClassVar[NodeKind]  # what `emit` writes for it
    __tm_prefix__: ClassVar[str]  # set when a package registers the class
    __tm_cs__: ClassVar[str]  # likewise: the control sequence, see `control_name`
    cs: ClassVar[str | None] = None  # the TeX name, when it is not prefix + class name (`cs = "includegraphics"`)
    syntax: ClassVar[Syntax] = Syntax.LATEX2E  # the names `cs` may have: `Syntax.EXPL3` allows `_` and `:`
    defined_by: ClassVar[Library | None] = None  # the library block that defines it, so it renders no definition
    __tm_package__: ClassVar[object]  # the `Package` it was registered with
    meta: ClassVar[
        Mapping[str, object]
    ] = {}  # the schema's `x-` keys on this component (`meta = {"audience": "deck"}`)

    def __init_subclass__(
        cls, *, unused: Sequence[str] = (), abstract: bool = False, kw_only: bool | None = None, **kwargs: Any
    ) -> None:
        """`unused`, `abstract` and `kw_only` are read by `__pydantic_init_subclass__`, once pydantic has the fields."""
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
        return violations_of(self, type(self).__name__)  # pyright: ignore[reportArgumentType]

    def render(self) -> str:
        """The TeX for this node (`\\acFact{...}`, or `\\begin{acCardBack}` ... `\\end{acCardBack}`): pure and
        deterministic (D2). Raises an `ExceptionGroup` if the node is invalid."""
        return render_of(self)  # pyright: ignore[reportArgumentType]


def _build(cls: type[_Node], unused: Sequence[str], *, abstract: bool, kw_only: bool | None) -> None:
    """Read a declared class once pydantic has its fields. An abstract base needs no name a control word could have
    and no docstring: it is never registered."""
    cls.__tm_abstract__ = abstract
    cls.__tm_kw_only__ = cls.__tm_kw_only__ if kw_only is None else kw_only
    cls.__tm_doc__ = doc = "" if abstract else document_of(cls)
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


@dataclass_transform(frozen_default=True, kw_only_default=True, field_specifiers=(field, arg))
class Command(_Node):
    """A TeX command (`\\newcommand`) whose arguments are the class's fields."""

    __tm_node__ = NodeKind.COMMAND
    __tm_inline__: ClassVar[Source | None]

    @classmethod
    def __pydantic_init_subclass__(
        cls, *, unused: Sequence[str] = (), abstract: bool = False, kw_only: bool | None = None, **kwargs: Any
    ) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        cls.__tm_inline__ = _source(cls, "body")
        _build(cls, unused, abstract=abstract, kw_only=kw_only)

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

    if TYPE_CHECKING:  # at run time the metaclass builds the node (`_Meta.__call__`)

        def __init__(self, *content: Node, **args: object) -> None: ...

    @classmethod
    def __pydantic_init_subclass__(
        cls, *, unused: Sequence[str] = (), abstract: bool = False, kw_only: bool | None = None, **kwargs: Any
    ) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        cls.__tm_inline__ = (_source(cls, "begin"), _source(cls, "end"))
        cls.__tm_grammar__ = _grammar(cls)
        _build(cls, unused, abstract=abstract, kw_only=kw_only)
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


class Passthrough(_Node, kw_only=False):
    """TeX written as it is (B3): a layout `\\vspace` between components. It claims no control sequence; a grammar must
    list it (`Passthrough.times.any()`, or `Anywhere(Passthrough)`) before an environment accepts one."""

    __tm_node__ = NodeKind.PASSTHROUGH
    tex: Raw
    __tm_args__: ClassVar[tuple[Arg, ...]] = (Arg("tex", RAW_BODY, hint=Raw),)
    __tm_doc__: ClassVar[str] = "TeX written as it is."
    __tm_kw_only__: ClassVar[bool] = False

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


@dataclasses.dataclass(frozen=True)
class Children:
    """The schema of a list of nodes in data: a union, told apart by `"type"`, of the components an environment's
    grammar names, or (given a package) of every command and environment it registers and `Passthrough`; and `Comment`
    and the package's comment classes. Plumbing for `spec`."""

    owner: "type[Environment] | Package"

    def __get_pydantic_core_schema__(self, source: object, handler: pydantic.GetCoreSchemaHandler) -> CoreSchema:
        if isinstance(self.owner, type):
            package = typing.cast("Package | None", getattr(self.owner, "__tm_package__", None))
            kinds = [k for t in self.owner.__tm_grammar__ for k in concrete_kinds(t.kind)]
        else:
            package = self.owner
            kinds = [c for c in package.visible if issubclass(c, Command | Environment)] + [Passthrough]
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
