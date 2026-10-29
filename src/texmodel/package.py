"""A `Package` is the container: its commands render to one `.sty` (G1), deterministically.

An adopted package (M9) is the other way round: the `.sty` is hand-written, the components only declare its interface,
and `check_interface` compares the two.
"""

import dataclasses
import importlib.metadata
import inspect
import re
import textwrap
import types
import typing
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Annotated, Any, NamedTuple

from pydantic.fields import FieldInfo

from ._internal.emit import INDENT, call_line, emit
from ._internal.options import Option, OptionKind, choice_kind
from ._internal.pieces import template_text
from ._internal.render import (
    EnvSpec,
    Spec,
    ValueSpec,
    addressed,
    canonical,
    check_references,
    header_lines,
    lint_library,
    render_command,
    render_environment,
    render_library,
    render_value,
    require_lines,
    signature,
    undeclared,
)
from ._internal.scan import scan_colours, scan_counters, scan_declarations
from ._internal.specs import env_spec_of, spec_of, value_spec_of
from ._internal.values import fill_text
from .body import Comment, Library, Syntax, TemplateRef, Whitespace
from .components import (
    AnyValue,
    Command,
    Environment,
    Node,
    Passthrough,
    Value,
    control_name,
)
from .document import OPTION, Document
from .drift import stamp
from .errors import DeclarationError, Violation
from .interface import XCOLOR, colour_of, constraint_of
from .plan import Line, Plan, Span
from .preamble import Entry, PdfInfo, RequireMetadata
from .testing import Component, stub_tex
from .types import PROCESS, Choice, Length, Raw, balanced

_NAME = re.compile(r"[a-z][a-z0-9-]*")
_PREFIX = re.compile(r"[a-z]*")  # empty: the package of a standard TeX library, whose names carry none
_DATE = re.compile(r"\d{4}/\d{2}/\d{2}")  # \ProvidesPackage's date slot: YYYY/MM/DD (G3)


_LIBRARY_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_OPTION_NAME = re.compile(r"[a-z]+(?:-[a-z]+)*")  # a LaTeX key: letters, `-` between words (it names a macro too)
_BAD_OPTION = re.compile(r"[%\\\n]")  # a comment, a control sequence or a line end


def _package_option(option: str) -> bool:
    """One package option as written in `[...]`: `table`, `margin=10mm`, `colorprofiles={A=a.icc}`. Braces balance, and
    outside braces nothing ends the option list early."""
    outside = re.sub(r"\{[^{}]*\}", "", option)
    return (
        bool(option.strip())
        and balanced(option)
        and not _BAD_OPTION.search(option)
        and not re.search(r"[\[\]]", outside)
    )


def _passthroughs(node: Node, path: str) -> Iterator[tuple[str, Passthrough]]:
    """Every `Passthrough` in a tree with its plan path."""
    if isinstance(node, Passthrough):
        yield path, node
    elif isinstance(node, Environment):
        for i, child in enumerate(node.content):
            yield from _passthroughs(child, f"{path}/{type(child).__name__}[{i}]")


GENERATOR_VERSION: str | None = None
"""Set in a copy of texmodel with no installed metadata (embedded in a wheel) to the version it was built from."""


def generator_version() -> str:
    """`X.Y.Z` of texmodel (`GENERATOR_VERSION`, else the installed metadata), without dev or local parts, so output
    does not churn per commit (G7)."""
    m = re.match(r"\d+\.\d+\.\d+", GENERATOR_VERSION or importlib.metadata.version("texmodel"))
    return m[0] if m else "0.0.0"


class _Defs(NamedTuple):
    """What a library defines: control sequences with their signatures, and names of other kinds (colours, counters)."""

    controls: dict[str, str]
    others: frozenset[tuple[str, str]]

    def pairs(self) -> list[tuple[str, str]]:
        return [*(("control", n) for n in self.controls), *sorted(self.others)]


def _concrete(cls: type[Command] | type[Environment]) -> None:
    if cls.__tm_abstract__:
        raise DeclarationError(
            f"{cls.__qualname__}: an abstract base is not registered",
            code="TM-M043",
            path=cls.__name__,
            hint="register the subclasses",
        )


def _shown(kind: str, name: str) -> str:
    return f"\\{name}" if kind == "control" else f"{kind} {name}"


def _compare(who: str, lib: str, defs: _Defs, wanted: Sequence[tuple[str, str, str]]) -> list[Violation]:
    """`who` wants these names (kind, name, signature) from library `lib`: each must be defined, as declared."""
    out: list[Violation] = []
    for kind, name, want in wanted:
        if (kind, name) not in defs.pairs():
            out.append(
                Violation("TM-C010", who, f"{_shown(kind, name)} is declared but library {lib} does not define it")
            )
        elif kind == "control" and canonical(defs.controls[name]) != canonical(want):
            out.append(
                Violation(
                    "TM-C011",
                    who,
                    f"{_shown(kind, name)}: declared {want or 'without arguments'}, library {lib} defines "
                    f"{defs.controls[name] or 'no arguments'}",
                    hint="change the declaration or the library so they agree",
                )
            )
    return out


def _field_data(spec: object) -> tuple[object, object]:
    """What makes two field declarations the same: the default and the `field(doc=, meta=)` data."""
    if isinstance(spec, FieldInfo):
        return spec.default, tuple(spec.metadata)
    return spec, ()


def declared(text: str) -> frozenset[str]:
    """The control sequences `text` declares (`bbName`, no backslash), by the forms the adoption scanner reads (see
    `check_interface`), not by `\\def`, `\\let` or an expl3 definer. A colour or a counter is not one."""
    return frozenset(scan_declarations(text))


def setting_line(value: AnyValue) -> str:
    """The line that sets `value` for a document: `\\setlength{\\acGap}{3mm}`, `\\renewcommand{\\acName}{R\\&D}`,
    `\\acDrafttrue`. It is what `Package.plan` writes for each of a `Document`'s `settings`."""
    cls = type(value)
    return cls.__tm_kind__.setting(*addressed(cls.__tm_prefix__, cls.__name__, cls.cs), value.value, cls.colour_name)


def _document_of(body: Sequence[Node | Document]) -> Document:
    """The `Document` a call gave: one, alone, or the bare nodes of a plain one."""
    given = [b for b in body if isinstance(b, Document)]
    if given and len(body) > 1:
        raise TypeError("a Document is the whole document: give it alone, or give only nodes")
    return given[0] if given else Document(*typing.cast("Sequence[Node]", body))


def _tex_of(item: Raw | Entry) -> Raw:
    """The `Raw` a slot item stands for."""
    return item if isinstance(item, Raw) else item.raw()


def _node_lines(node: Node, path: str, depth: int = 0) -> Iterator[Line]:
    """The lines a node renders at `depth`; children are indexed within their parent, as `violations()` paths are."""
    if not isinstance(node, Command | Environment):
        yield from (Line(path, tex) for tex in emit(node, depth).splitlines())
        return
    pad = INDENT * depth
    call, found = call_line(node)
    shift = len(pad)  # a multi-line call has no one-line spans
    spans = tuple(Span(arg, start + shift, end + shift) for arg, start, end in found) if "\n" not in call else ()
    yield from (Line(path, tex, spans) for tex in (pad + call).splitlines())
    if isinstance(node, Environment):
        for i, child in enumerate(node.content):
            yield from _node_lines(child, f"{path}/{type(child).__name__}[{i}]", depth + 1)
        yield Line(path, f"{pad}\\end{{{control_name(type(node))}}}")


class Package:
    def __init__(
        self,
        name: str,
        *,
        prefix: str,
        version: str = "0.0.0",
        date: str | None = None,
        description: str = "",
        header: str = "",
        document_class: str = "article",
        adopted: bool = False,
        builtin: bool = False,
        whitespace: Whitespace = Whitespace.KEEP,
        comments: Sequence[type[Comment]] = (),
        base: "Package | None" = None,
    ) -> None:
        if not _NAME.fullmatch(name):
            raise DeclarationError(f"package name {name!r} must match [a-z][a-z0-9-]*", code="TM-P001")
        if not _PREFIX.fullmatch(prefix):
            raise DeclarationError(f"prefix {prefix!r} must be lowercase letters, or empty", code="TM-P002")
        if date is not None and not _DATE.fullmatch(date):
            raise DeclarationError(f"date {date!r} must be YYYY/MM/DD (\\ProvidesPackage's date slot)", code="TM-P003")
        if not _NAME.fullmatch(document_class):
            raise DeclarationError(f"document class {document_class!r} must match [a-z][a-z0-9-]*", code="TM-P004")
        self.name, self.prefix, self.version, self.date, self.description = name, prefix, version, date, description
        self.header = header  # comment lines under the generator's line, for what the file's readers should know
        self.document_class = document_class
        self.whitespace = whitespace  # the policy of a body piece that names none (M8)
        self.adopted = adopted  # the `.sty` is hand-written; components only declare it (M9)
        self.builtin = builtin  # always loaded (the LaTeX kernel): calling it requires no package
        self.comments = tuple(comments)  # the comment classes data may hold, besides `Comment`, in its environments
        self.base = base  # the package this one specializes: loaded first, its names are looked up through it
        self._requires: list[tuple[Package, tuple[str, ...]]] = []  # `require()`, in order
        self._items: list[Spec | EnvSpec | ValueSpec | Library] = []  # registration order is output order
        self._controls: dict[str, str] = {}  # control sequence -> qualname of its declarer
        self._calls: list[type] = []  # components its bodies call, in order
        self._colours: dict[str, str] = {}  # colour name -> qualname; its own namespace
        self._classes: list[type] = []  # every registered class, in registration order
        self._made: dict[tuple[str, str], tuple[tuple[object, ...], type]] = {}  # `make_*`: (kind, name) -> data, class
        self._options: dict[str, Option] = {}  # package options by name, in registration order (§21)
        if base is not None:
            self.require(base)

    def _add(
        self, spec: Spec | EnvSpec | ValueSpec, *claims: tuple[dict[str, str], str, str], rendered: bool = True
    ) -> None:
        """Claim names (table, key, how to show it); a collision is an error here, not at \\begin{document} (M7). A
        component a library defines claims its name and renders nothing."""
        for table, key, shown in claims:
            if key in table:
                raise DeclarationError(
                    f"{spec.qualname}: {shown} is already declared by {table[key]}", code="TM-M007", path=spec.name
                )
        for table, key, _ in claims:
            table[key] = spec.qualname
        if rendered:
            self._items.append(spec)
        if not isinstance(spec, ValueSpec):
            self._calls.extend(spec.refs)

    def command[C: type[Command]](self, cls: C) -> C:
        """Register a command class."""
        _concrete(cls)
        spec = spec_of(cls, declared_only=self.adopted, whitespace=self.whitespace)
        self._own_library(cls)
        if not self.adopted and cls.defined_by is None:
            render_command(self.prefix, spec)  # lints the body now, so a bad body is refused at import
        control = self._control(spec)
        self._add(spec, (self._controls, control, f"\\{control}"), rendered=cls.defined_by is None)
        cls.__tm_prefix__, cls.__tm_package__, cls.__tm_cs__ = self.prefix, self, control
        self._classes.append(cls)
        return cls

    def _own_library(self, cls: type[Command] | type[Environment] | type[AnyValue]) -> None:
        """The block that defines a component is this package's (`TM-M033`)."""
        if cls.defined_by is not None and cls.defined_by.owner is not self:
            raise DeclarationError(
                f"{cls.__qualname__}: defined_by {cls.defined_by.name!r}, a library of another package",
                code="TM-M033",
                path=cls.__name__,
                hint="declare the component in the package whose library defines it",
            )

    def library(
        self, name: str, source: str | TemplateRef, *, syntax: Syntax = Syntax.LATEX2E, fill: object | None = None
    ) -> Library:
        """TeX carried into the `.sty` as it is (§21), among the items in registration order: dedented, blank edges
        removed, `%` and `#name` untouched. `Syntax.EXPL3` wraps it in `\\ExplSyntaxOn` / `\\ExplSyntaxOff`. A relative
        `TemplateRef` is relative to the calling module. Name a component's `defined_by` to declare what it defines.

        `fill` (a mapping, a dataclass or a pydantic model) fills the `<<name>>` holes of the text, typed: `str` is
        escaped, `Raw` passes through, lengths and colours are written as they are (`<<a.b>>` reaches into a nested
        model). Without `fill` the text is carried exactly as it is."""
        if not _LIBRARY_NAME.fullmatch(name):
            raise DeclarationError(
                f"library name {name!r} must match [A-Za-z][A-Za-z0-9_-]*", code="TM-M001", path=name
            )
        if any(isinstance(i, Library) and i.name == name for i in self._items):
            raise DeclarationError(f"library {name!r} is already declared", code="TM-M007", path=name)
        origin = "inline"
        if isinstance(source, TemplateRef):
            source, origin = (
                template_text(source, inspect.stack(0)[1].frame.f_globals["__name__"], name),
                source.path.name,
            )
        text = textwrap.dedent(source).strip("\n")
        lib = Library(
            name, text if fill is None else fill_text(text, fill, syntax, f"library {name}"), syntax, origin, self
        )
        lint_library(lib)
        self._items.append(lib)
        return lib

    def _control(self, spec: Spec | EnvSpec) -> str:
        """The control sequence: its `cs`, else prefix + class name (which needs a prefix)."""
        if spec.cs is None and not self.prefix:
            raise DeclarationError(
                f"{spec.qualname}: a package with no prefix names its commands with `cs`",
                code="TM-P011",
                path=spec.name,
                hint=f'add cs = "..." (the TeX name, e.g. {spec.name.lower()!r}) to the class',
            )
        return spec.cs or self.prefix + spec.name

    def environment[E: type[Environment]](self, cls: E) -> E:
        """Register an environment class: `\\newenvironment` with its begin and end bodies."""
        _concrete(cls)
        spec = env_spec_of(cls, declared_only=self.adopted, whitespace=self.whitespace)
        self._own_library(cls)
        if not self.adopted and cls.defined_by is None:
            render_environment(self.prefix, spec)  # lints both bodies now
        control = self._control(spec)
        self._add(spec, (self._controls, control, f"\\{control}"), rendered=cls.defined_by is None)
        cls.__tm_prefix__, cls.__tm_package__, cls.__tm_cs__ = self.prefix, self, control
        self._classes.append(cls)
        return cls

    def value[V: type[AnyValue]](self, cls: V) -> V:
        """Register a value class: `\\newlength`, `\\definecolor`, `\\newif` or `\\newcommand` by its type (M1a)."""
        return self._value(cls, rendered=cls.defined_by is None)

    def _value[V: type[AnyValue]](self, cls: V, *, rendered: bool) -> V:
        """Register a value; `rendered` puts its declaration among the items (an option's is in the options section)."""
        spec = value_spec_of(cls)
        if self.adopted and not spec.kind.adoptable:
            raise DeclarationError(
                f"{cls.__qualname__}: an adopted package can declare a Value[Text] or Value[Raw] only",
                code="TM-P005",
                path=spec.name,
                hint="declare a length, colour or flag the hand-written package defines as a Command with no arguments",
            )
        self._own_library(cls)
        if spec.default is None and not self.adopted and not spec.kind.bare and cls.defined_by is None:
            raise DeclarationError(f"{cls.__qualname__}: no default", code="TM-M013", path=spec.name)
        tables = {"control": self._controls, "colour": self._colours}
        claims = [
            (tables[table], key, shown)
            for table, key, shown in spec.kind.claims(*addressed(self.prefix, spec.name, spec.cs), spec.alias)
        ]
        self._add(spec, *claims, rendered=rendered)
        if not spec.kind.named:  # a colour is not a control sequence
            cls.__tm_cs__ = "".join(addressed(self.prefix, spec.name, spec.cs))
        cls.__tm_prefix__ = self.prefix
        self._classes.append(cls)
        return cls

    def option(
        self,
        name: str,
        *,
        doc: str,
        flag: bool | None = None,
        length: Length | None = None,
        choice: Choice | None = None,
        inverse: str | None = None,
        cs: str | None = None,
    ) -> type[AnyValue]:
        """Declare a package option (§21) and return the value it sets: a `flag` (`crop`, `crop=false`, and the
        `inverse` key `nocrop`), a `length` (`bleed=2mm`) or a `choice` (`accent=moss`, a member's name in lowercase);
        the argument given is its default. The value's class is the option's name in CamelCase (`show-crop` is
        `ShowCrop`), its control sequence `<prefix><Class>` unless `cs` names it. A module declares the options it
        needs when it is added to a package: the same name declared again the same way is the option declared first;
        another default, kind, inverse or `cs` is `TM-M073`. A document sets an option as it sets any value, and it is
        written where it takes effect, in `\\usepackage[...]`."""
        given = [(k, v) for k, v in ((OptionKind.FLAG, flag), (OptionKind.LENGTH, length), (OptionKind.CHOICE, choice))]
        chosen = [(k, v) for k, v in given if v is not None]
        problem = (
            f"{name!r} is not an option name: lowercase letters, `-` between words"
            if not _OPTION_NAME.fullmatch(name)
            else "give one of flag=, length= or choice=: the kind of the option and its default"
            if len(chosen) != 1
            else f"inverse {inverse!r} is not an option name, or names the option itself"
            if inverse is not None and (not _OPTION_NAME.fullmatch(inverse) or inverse == name)
            else "only a flag has an inverse"
            if inverse is not None and chosen[0][0] is not OptionKind.FLAG
            else "a package with no prefix (or no \\usepackage of its own) needs `cs=` and a \\usepackage"
            if self.builtin or (not self.prefix and cs is None)
            else None
        )
        if problem:
            raise DeclarationError(f"{self.name}: option {problem}", code="TM-M072", path=name)
        kind, default = chosen[0]
        same = (kind, default, inverse, cs)
        taken = {o.inverse: o.name for o in self._options.values() if o.inverse} | {n: n for n in self._options}
        if (earlier := self._options.get(name)) is not None:
            if earlier.same != same:
                raise DeclarationError(
                    f"{self.name}: option {name!r} is declared again differently: (kind, default, inverse, cs) "
                    f"{earlier.same!r}, now {same!r}",
                    code="TM-M073",
                    path=name,
                    hint="two modules share an option only when they declare it the same way",
                )
            return earlier.value
        if (clash := next((k for k in (name, inverse) if k in taken), None)) is not None:
            raise DeclarationError(
                f"{self.name}: option key {clash!r} is already the key of option {taken[clash]!r}",
                code="TM-M073",
                path=name,
            )
        hint: object = (
            bool
            if kind is OptionKind.FLAG
            else Length
            if kind is OptionKind.LENGTH
            else Annotated[type(default), choice_kind(type(typing.cast("Choice", default)))]
        )
        namespace = {"__doc__": doc, "__module__": self.name, "default": default} | ({"cs": cs} if cs else {})
        made = types.new_class(
            "".join(word.capitalize() for word in name.split("-")),
            (Value[hint],),
            exec_body=lambda ns: ns.update(namespace),
        )
        value = self._value(typing.cast("type[AnyValue]", made), rendered=False)
        self._options[name] = Option(name, kind, default, inverse, cs, value)
        return value

    def _option_lines(self) -> list[str]:
        """The options section (§21): each option's register with its default, the keys, one `\\ProcessKeyOptions`."""
        declared = [
            line
            for o in self._options.values()
            for line in render_value(self.prefix, value_spec_of(o.value)).splitlines()
        ]
        keys = [f"    {k}" for o in self._options.values() for k in o.keys(o.value.__tm_cs__)]
        return [
            *declared,
            "\\ExplSyntaxOn",
            f"\\keys_define:nn {{ {self.name} }}",
            "  {",
            *keys,
            "  }",
            f"\\ProcessKeyOptions [ {self.name} ]",
            "\\ExplSyntaxOff",
        ]

    def _option_of(self, cls: type) -> tuple["Package", Option] | None:
        """The package of this family that declared `cls` as its option, and the option."""
        return next(((p, o) for p in self._lineage() for o in p._options.values() if o.value is cls), None)  # noqa: SLF001

    def make_command(
        self,
        name: str,
        doc: str,
        *,
        fields: Mapping[str, tuple[object, object]] | None = None,
        body: str | None = None,
        defined_by: Library | None = None,
        cs: str | None = None,
        module: str | None = None,
    ) -> type[Command]:
        """Declare and register a command from data, for names a program decides at run time. `fields` maps a field
        name to `(hint, field(...))` in TeX order, as `create_model` does (`{"name": (Raw, field(doc="the name"))}`);
        `body` is TeX, or `defined_by` the library block that defines it. Declaring the same data again returns the
        class made first; other data under the name is `TM-M007`. `module` (default: the package's name) is shown in
        messages."""
        given = dict(fields or {})
        data = (doc, cs, body, defined_by, tuple((n, h, _field_data(f)) for n, (h, f) in given.items()))
        return self._make("command", name, data, module, self.command, Command, doc, cs, defined_by, body, given)

    def make_value(
        self,
        name: str,
        kind: object,
        doc: str,
        *,
        default: object = None,
        colour_name: str | None = None,
        defined_by: Library | None = None,
        cs: str | None = None,
        module: str | None = None,
    ) -> type[AnyValue]:
        """Declare and register a value from data: `kind` is `Length`, `Colour`, `bool`, `Text`, `Raw` or a package's
        own; `defined_by` is the library block that defines it. Declaring the same data again returns the class made
        first; other data under the name is `TM-M007`."""
        data = (kind, doc, default, colour_name, defined_by, cs)
        return self._make(
            "value", name, data, module, self.value, Value[kind], doc, cs, defined_by, None, {}, default, colour_name
        )

    def _make(
        self,
        what: str,
        name: str,
        data: tuple[object, ...],
        module: str | None,
        register: Callable[[Any], type],
        base: type,
        doc: str,
        cs: str | None,
        defined_by: Library | None,
        body: str | None,
        fields: Mapping[str, tuple[object, object]],
        default: object = None,
        colour_name: str | None = None,
    ) -> Any:  # noqa: ANN401  # the caller's `register` fixes the class's type
        module = module or self.name
        earlier = self._made.get((what, name))
        if earlier is not None:
            if earlier[0] != data:
                raise DeclarationError(
                    f"{module}.{name}: declared again with other data than {earlier[1].__module__}.{name}",
                    code="TM-M007",
                    path=name,
                    hint="the same name is declared once, or with identical data",
                )
            return earlier[1]
        namespace: dict[str, object] = {"__doc__": doc, "__module__": module}
        if cs is not None:
            namespace["cs"] = cs
        if defined_by is not None:
            namespace["defined_by"] = defined_by
        if what == "command":
            namespace |= {"body": body} if body is not None else {}
            namespace["__annotations__"] = {n: h for n, (h, _) in fields.items()}
            namespace |= {n: f for n, (_, f) in fields.items()}
        else:
            namespace |= {"colour_name": colour_name} if colour_name is not None else {}
            namespace |= {"default": default} if default is not None else {}
        cls = register(types.new_class(name, (base,), exec_body=lambda ns: ns.update(namespace)))
        self._made[what, name] = data, cls
        return cls

    @property
    def registered(self) -> tuple[type, ...]:
        """Every registered command, environment and value class, in registration order."""
        return tuple(self._classes)

    @property
    def options(self) -> tuple[type[AnyValue], ...]:
        """The values this package's options set (`option`), in declaration order."""
        return tuple(o.value for o in self._options.values())

    @property
    def visible(self) -> tuple[type, ...]:
        """Every command, environment and value class a document of this package may name: the base's, then this
        package's own, which replace a base class of the same name."""
        found = {c.__name__: c for p in self._lineage() for c in p.registered}
        return tuple(found.values())

    def value_named(self, name: str) -> type[AnyValue] | None:
        """The value class called `name` that `visible` holds, or `None`."""
        found = next((c for c in self.visible if c.__name__ == name), None)
        return typing.cast("type[AnyValue]", found) if found and issubclass(found, Value) else None

    def colour_constraints(self) -> dict[str, frozenset[str] | None]:
        """Every colour name an argument may use here, with the plates it may ink: this package's colour values and its
        base chain's, the colours its LaTeX libraries define (any process plate), and xcolor's base names. `None`
        inks nothing (`white`)."""
        found = dict(XCOLOR)
        for p in self._lineage():
            for cls in p.registered:
                if issubclass(cls, Value) and cls.__tm_kind__.named:
                    named = typing.cast("type[Value[Any]]", cls)
                    found[colour_of(named)] = constraint_of(named)
            for item in p._items:  # noqa: SLF001
                if isinstance(item, Library) and item.syntax is Syntax.LATEX2E:
                    found |= dict.fromkeys(scan_colours(item.text) - found.keys(), PROCESS)
        return found

    def _lineage(self) -> list["Package"]:
        """The base chain, farthest base first, this package last."""
        return [*(self.base._lineage() if self.base else ()), self]  # noqa: SLF001

    @property
    def known_controls(self) -> dict[str, str]:
        """Control sequence -> declarer, over the base chain; this package's own replace a base's."""
        return {k: v for p in self._lineage() for k, v in p._controls.items()}  # noqa: SLF001

    def require(self, package: "Package", *, options: Sequence[str] = ()) -> None:
        """Load `package` with `\\RequirePackage[options]{name}` in this package's `.sty`, before the packages its
        components need. For a library whose commands bodies do not call (microtype, hyphenat) or that takes options."""
        if package.builtin:
            raise DeclarationError(f"{package.name} is always loaded", code="TM-P008", path=self.name)
        if bad := [o for o in options if not _package_option(o)]:
            raise DeclarationError(
                f"package option {bad[0]!r}: not empty, balanced braces, no % or \\ or [ ] outside braces",
                code="TM-P009",
                hint="e.g. 'table', 'margin=10mm', 'colorprofiles={A=a.icc,X=b.icc}'",
            )
        if any(p is package for p, _ in self._requires):
            raise DeclarationError(f"{package.name} is already required by {self.name}", code="TM-P010", path=self.name)
        self._requires.append((package, tuple(options)))

    @property
    def depends_on(self) -> tuple["Package", ...]:
        """The other packages this one requires or whose components its bodies call, in first-use order."""
        called = (typing.cast("Package", t.__tm_package__) for t in self._calls)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        needed = (p for s in self._items if isinstance(s, ValueSpec) for p in s.needs if not isinstance(p, str))
        found = (*(p for p, _ in self._requires), *called, *needed)
        return tuple(dict.fromkeys(p for p in found if p is not self and not p.builtin))

    def require_entries(self) -> list[tuple[str, tuple[str, ...]]]:
        """What the `.sty` loads: `require()`d packages in order with their options, then, sorted, the packages the
        values need (M14) and the components call that are not already loaded; computed, never collected by mutation."""
        explicit = [(p.name, o) for p, o in self._requires]
        needs = {p for s in self._items if isinstance(s, ValueSpec) for p in s.needs if isinstance(p, str)}
        rest = sorted({*needs, *(p.name for p in self.depends_on)} - {n for n, _ in explicit})
        return [*explicit, *((n, ()) for n in rest)]

    @property
    def required_packages(self) -> tuple[str, ...]:
        """The names `require_entries` loads, in order."""
        return tuple(n for n, _ in self.require_entries())

    def _check_cycles(self, path: tuple["Package", ...] = ()) -> None:
        """A package that (through others) requires itself cannot load (`TM-P007`)."""
        if self in path:
            chain = " -> ".join(p.name for p in (*path[path.index(self) :], self))
            raise DeclarationError(f"packages require each other: {chain}", code="TM-P007", path=self.name)
        for dependency in self.depends_on:
            dependency._check_cycles((*path, self))  # noqa: SLF001

    def render(self, *, version: str | None = None) -> str:
        """The `.sty` text, that of `render_plan(version=)`."""
        return self.render_plan(version=version).text

    def render_plan(self, *, version: str | None = None) -> Plan:
        """The `.sty` as lines with provenance (§21): `header`, `requires`, then one path per component or value
        (`Fact`, `FactGap`); the blank line before an item is the item's. `version` is the generator's, recorded in the
        header; default the installed texmodel's.

        Body references are checked here, not at registration: a body may name a component declared after it, so the
        family is only complete once someone asks for output (`files()` and `texmodel check` both do) (M8, G2).
        """
        if self.adopted:
            raise DeclarationError(
                f"{self.name}: an adopted package renders no .sty", code="TM-P006", hint="the hand-written one is it"
            )
        self._check_cycles()
        if duplicates := self._duplicates():
            raise DeclarationError(duplicates[0], code="TM-P012", path=self.name, hint="define each name once")
        for s in self._items:
            if isinstance(s, Spec):
                check_references(self.prefix, s, s.body, self._controls)
            elif isinstance(s, EnvSpec):
                check_references(self.prefix, s, s.begin + "\n" + s.end, self._controls)
        head = header_lines(
            self.name, self.version, self.date, self.description, stamp(version or generator_version()), self.header
        )
        requires = require_lines(self.require_entries())
        lines = [
            *(Line("header", tex) for tex in head),
            Line("requires", ""),
            *(Line("requires", tex) for tex in requires),
            *([Line("requires", "")] if requires else []),
        ]
        if self._options:  # right after the packages, so everything below reads the options (§21)
            lines += [*(Line("options", tex) for tex in self._option_lines()), Line("options", "")]
        elif not self._items:
            lines.append(Line("requires", ""))  # the file ends with the empty body's own blank line
        for n, s in enumerate(self._items):
            text = self._render_item(s).splitlines()
            lines += [Line(s.name, ""), *(Line(s.name, tex) for tex in text)] if n else [Line(s.name, t) for t in text]
        return Plan(tuple(lines))

    def _render_item(self, s: Spec | EnvSpec | ValueSpec | Library) -> str:
        if isinstance(s, Library):
            return render_library(s)
        if isinstance(s, ValueSpec):
            return render_value(self.prefix, s)
        return render_command(self.prefix, s) if isinstance(s, Spec) else render_environment(self.prefix, s)

    def check_interface(self, *sources: str) -> list[Violation]:
        """Every declared component is defined in `sources` (the hand-written TeX) with the signature declared (M9).

        Read by `texmodel check` for an adopted package. A name that `sources` define some other way than
        `\\newcommand`, `\\providecommand`, `\\newenvironment` or an xparse `\\NewDocumentCommand` counts as missing. A
        public name (`<prefix>Name`) the sources define that nothing declares is `TM-C025`, as a library's is `TM-C012`.
        """
        found = scan_declarations("\n".join(sources))
        out: list[Violation] = []
        for s in (i for i in self._items if not isinstance(i, Library)):
            control, want = (
                (s.cs or self.prefix + s.name) if not isinstance(s, ValueSpec) else self.prefix + s.name,
                "" if isinstance(s, ValueSpec) else signature(s.args),
            )
            if control not in found:
                out.append(Violation("TM-C010", s.name, f"\\{control} is declared but the sources do not define it"))
            elif canonical(found[control]) != canonical(want):
                out.append(
                    Violation(
                        "TM-C011",
                        s.name,
                        f"\\{control}: declared {want or 'without arguments'}, the sources define "
                        f"{found[control] or 'no arguments'}",
                        hint="change the declaration or the package so they agree",
                    )
                )
        known = self.known_controls
        return out + [
            Violation(
                "TM-C025",
                self.name,
                f"\\{n} is defined by the sources but nothing declares it",
                hint="declare it, or give the helper a name outside the public namespace (an @ in it)",
            )
            for n in found
            if self._public(n) and n not in known
        ]

    def _public(self, name: str) -> bool:
        """`<prefix>Name`: a name in the package's public namespace (none for a package without a prefix)."""
        return bool(self.prefix) and re.fullmatch(rf"{self.prefix}[A-Z][A-Za-z]*", name) is not None

    def _parts(self) -> dict[str, "_Defs"]:
        """What each library defines, by library name, in the forms `scan` reads; a library written in expl3 is not
        read."""
        return {
            i.name: _Defs(
                scan_declarations(i.text),
                frozenset(
                    [*(("colour", n) for n in scan_colours(i.text)), *(("counter", n) for n in scan_counters(i.text))]
                ),
            )
            for i in self._items
            if isinstance(i, Library) and i.syntax is Syntax.LATEX2E
        }

    def _duplicates(self) -> list[str]:
        """A name defined twice: by two libraries, or by a library and a component or value this package renders."""
        owner: dict[tuple[str, str], str] = {}
        for s in (i for i in self._items if not isinstance(i, Library)):
            if isinstance(s, ValueSpec):
                names = [(t, k) for t, k, _ in s.kind.claims(*addressed(self.prefix, s.name, s.cs), s.alias)]
            else:
                names = [("control", s.cs or self.prefix + s.name)]
            owner.update(dict.fromkeys(names, s.name))
        out: list[str] = []
        for lib, defs in self._parts().items():
            for kind, name in defs.pairs():
                if (kind, name) in owner:
                    out.append(f"{_shown(kind, name)} is defined by {owner[kind, name]} and by library {lib}")
                owner.setdefault((kind, name), f"library {lib}")
        return out

    def check_parts(self) -> list[Violation]:
        """What each library defines against what this package declares (§21): a component or value with
        `defined_by` is defined by that library, with its signature (`TM-C010`, `TM-C011`), a public name
        (`<prefix>Name`) a library defines is declared (`TM-C012`), and no name is defined twice (`TM-C013`). Read by
        `texmodel check`."""
        parts = self._parts()
        out: list[Violation] = []
        for cls in (c for c in self._classes if issubclass(c, Command | Environment)):
            lib = cls.defined_by
            if lib is not None and lib.name in parts:
                out += _compare(
                    cls.__name__, lib.name, parts[lib.name], [("control", cls.__tm_cs__, signature(cls.__tm_args__))]
                )
        for member in self._classes:
            if not issubclass(member, Value):
                continue
            value = typing.cast("type[Value[object]]", member)
            lib = value.defined_by
            if lib is not None and lib.name in parts:
                names = value.__tm_kind__.must_define(
                    *addressed(self.prefix, value.__name__, value.cs), value.colour_name
                )
                out += _compare(value.__name__, lib.name, parts[lib.name], [(t, k, "") for t, k, _ in names])
        for lib, defs in parts.items():
            out += [
                Violation(
                    "TM-C012",
                    lib,
                    f"\\{n} is defined by library {lib} but nothing declares it",
                    hint="declare it, or give the helper a name outside the public namespace (an @ in it)",
                )
                for n in defs.controls
                if self._public(n) and n not in self._controls
            ]
        return out + [Violation("TM-C013", self.name, message) for message in self._duplicates()]

    def plan(self, *body: Node | Document) -> Plan:
        """A complete `.tex` as lines with provenance (D1a, D2, B2): pure, deterministic, no I/O. The argument is one
        `Document`, or the nodes of one that has no options, settings or preamble.

        Everything wrong is reported at once, as an `ExceptionGroup` of `ValidationError` (E2).
        """
        document = _document_of(body)
        preamble, settings, options = document.preamble, document.settings, document.options
        problems = [v for node in document.content for v in node.violations()]
        problems += [
            Violation("TM-M015", path, f"\\{word} is not declared by this package", hint="declare it, or fix the name")
            for i, node in enumerate(document.content)
            for path, passthrough in _passthroughs(node, f"{type(node).__name__}[{i}]")
            for word in undeclared(self.prefix, passthrough.tex.tex, self.known_controls)
        ]
        problems += [
            Violation(
                "TM-M015",
                f"preamble.{slot}[{i}]",
                f"\\{word} is not declared by this package",
                hint="declare it, or fix the name",
            )
            for slot, i, item in preamble.items()
            for word in undeclared(self.prefix, _tex_of(item).tex, self.known_controls)
        ]
        problems += [
            Violation(
                "TM-C008",
                f"preamble.{slot}[{i}]",
                f"{type(item).__name__} does not belong in {slot}",
                hint=f"put it in {' or '.join(type(item).slots)}",
            )
            for slot, i, item in preamble.items()
            if not isinstance(item, Raw) and slot not in type(item).slots
        ]
        problems += [
            Violation(
                "TM-C009",
                f"preamble.{slot}[{i}]",
                "PdfInfo needs \\DocumentMetadata, which no RequireMetadata in before_class provides",
                hint="add RequireMetadata() to before_class",
            )
            for slot, i, item in preamble.items()
            if isinstance(item, PdfInfo) and not any(isinstance(x, RequireMetadata) for x in preamble.before_class)
        ]
        problems += [
            Violation("TM-C006", f"options[{i}]", f"class option {o!r} must match [A-Za-z0-9][A-Za-z0-9=.-]*")
            for i, o in enumerate(options)
            if not OPTION.fullmatch(o)
        ]
        if problems:
            raise ExceptionGroup("invalid document", [v.error() for v in problems])
        opts = f"[{','.join(options)}]" if options else ""

        def slot(name: str) -> list[Line]:
            return [
                Line(f"preamble.{name}[{i}]", tex)
                for i, raw in enumerate(getattr(preamble, name))
                for tex in _tex_of(raw).tex.splitlines()
            ]

        # An option is set where it takes effect, when its package loads: this package's in `\\usepackage[...]`, a
        # base's passed to it first. Every other setting goes right after the package, in the order given.
        routed = [(i, v, self._option_of(type(v))) for i, v in enumerate(settings)]
        own = [found[1].text(v.value) for _, v, found in routed if found and found[0] is self]
        passed = [
            Line(f"settings[{i}]", f"\\PassOptionsToPackage{{{found[1].text(v.value)}}}{{{found[0].name}}}")
            for i, v, found in routed
            if found and found[0] is not self
        ]
        use = f"\\usepackage[{','.join(own)}]{{{self.name}}}" if own else f"\\usepackage{{{self.name}}}"

        def values() -> list[Line]:
            return [Line(f"settings[{i}]", setting_line(v)) for i, v, found in routed if not found]

        return Plan(
            (
                Line("header", f"% {self.name} document -- {stamp(generator_version())}. Do not edit."),
                *slot("before_class"),
                Line("document", f"\\documentclass{opts}{{{self.document_class}}}"),
                *slot("before_package"),
                *passed,
                *([] if self.builtin else [Line("document", use)]),
                *values(),
                *slot("after_package"),
                Line("document", "\\begin{document}"),
                *(
                    line
                    for i, node in enumerate(document.content)
                    for line in _node_lines(node, f"{type(node).__name__}[{i}]")
                ),
                Line("document", "\\end{document}"),
            )
        )

    def document(self, *body: Node | Document) -> str:
        """The `.tex` text of `plan(...)`."""
        return self.plan(*body).text

    def test_document(self, *body: Node | Document, stub: Sequence[Component] = ()) -> str:
        """A `.tex` for testing `body` against stubs (§21): the real packages are loaded, then each class in `stub`
        is replaced by a macro that writes `texmodel:probe:callN=...` to the log instead of typesetting. Read the calls
        with `texmodel.run.testkit.run_probes` and `testing.Call.parse`; `testing.expand` gives the same calls
        without TeX."""
        document = _document_of(body)
        slots = document.preamble
        stubs = dataclasses.replace(slots, after_package=(*slots.after_package, Raw(stub_tex(stub))))
        return self.document(
            Document(*document.content, options=document.options, settings=document.settings, preamble=stubs)
        )

    def files(self, *, version: str | None = None) -> dict[str, str]:
        """Every generated file, by path relative to the output directory; an adopted package generates none."""
        return {} if self.adopted else {f"{self.name}.sty": self.render(version=version)}


__all__ = ["GENERATOR_VERSION", "Package", "declared", "generator_version", "setting_line"]
