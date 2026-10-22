"""A `Package` is the container: its commands render to one `.sty` (G1), deterministically.

An adopted package (M9) is the other way round: the `.sty` is hand-written, the components only declare its interface,
and `check_interface` compares the two.
"""

import dataclasses
import importlib.metadata
import inspect
import re
import textwrap
import typing
from collections.abc import Iterator, Sequence

from ._internal.render import (
    EnvSpec,
    Spec,
    ValueSpec,
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
from ._internal.scan import scan_declarations
from .body import Library, Syntax, TemplateRef, Whitespace, template_text
from .components import AnyValue, Command, Environment, Node, Passthrough, env_spec_of, spec_of, value_spec_of
from .drift import stamp
from .errors import DeclarationError, Violation
from .plan import Line, Plan, node_lines
from .preamble import Entry, PdfInfo, RequireMetadata, tex_of
from .testing import Component, stub_tex
from .types import Raw, balanced

_NAME = re.compile(r"[a-z][a-z0-9-]*")
_PREFIX = re.compile(r"[a-z]*")  # empty: the package of a standard TeX library, whose names carry none
_OPTION = re.compile(r"[A-Za-z0-9][A-Za-z0-9=.-]*")  # a class option is TeX, so it is not free text
_DATE = re.compile(r"\d{4}/\d{2}/\d{2}")  # \ProvidesPackage's date slot: YYYY/MM/DD (G3)


_LIBRARY_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
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


@dataclasses.dataclass(frozen=True)
class PreambleSlots:
    """TeX a document places around its class and package lines (D3), each slot a tuple of `Raw` or a typed entry
    (`InputPath`, `GraphicsPath`, `PassOption`, `RequireMetadata`, `PdfInfo`; one in a slot it does not belong in is
    `TM-C008`).

    `before_class` is where `\\DocumentMetadata` must go; `before_package` is for what the package needs when it
    loads (`\\input@path`, package options); `after_package` is for what needs it loaded (`\\graphicspath`,
    per-document `\\renewcommand`s). Public names of the package used here must be declared (M8).
    """

    before_class: tuple[Raw | Entry, ...] = ()
    before_package: tuple[Raw | Entry, ...] = ()
    after_package: tuple[Raw | Entry, ...] = ()

    def items(self) -> Iterator[tuple[str, int, Raw | Entry]]:
        """Every item with its slot name and index, in document order: the path is `preamble.<slot>[<index>]`."""
        for slot, found in (
            ("before_class", self.before_class),
            ("before_package", self.before_package),
            ("after_package", self.after_package),
        ):
            for i, item in enumerate(found):
                yield slot, i, item


def generator_version() -> str:
    """`X.Y.Z` of the installed texmodel, without dev or local parts, so output does not churn per commit (G7)."""
    m = re.match(r"\d+\.\d+\.\d+", importlib.metadata.version("texmodel"))
    return m[0] if m else "0.0.0"


class Package:
    def __init__(
        self,
        name: str,
        *,
        prefix: str,
        version: str = "0.0.0",
        date: str = "1970/01/01",
        description: str = "",
        document_class: str = "article",
        adopted: bool = False,
        builtin: bool = False,
        whitespace: Whitespace = Whitespace.KEEP,
    ) -> None:
        if not _NAME.fullmatch(name):
            raise DeclarationError(f"package name {name!r} must match [a-z][a-z0-9-]*", code="TM-P001")
        if not _PREFIX.fullmatch(prefix):
            raise DeclarationError(f"prefix {prefix!r} must be lowercase letters, or empty", code="TM-P002")
        if not _DATE.fullmatch(date):
            raise DeclarationError(f"date {date!r} must be YYYY/MM/DD (\\ProvidesPackage's date slot)", code="TM-P003")
        if not _NAME.fullmatch(document_class):
            raise DeclarationError(f"document class {document_class!r} must match [a-z][a-z0-9-]*", code="TM-P004")
        self.name, self.prefix, self.version, self.date, self.description = name, prefix, version, date, description
        self.document_class = document_class
        self.whitespace = whitespace  # the policy of a body piece that names none (M8)
        self.adopted = adopted  # the `.sty` is hand-written; components only declare it (M9)
        self.builtin = builtin  # always loaded (the LaTeX kernel): calling it requires no package
        self._requires: list[tuple[Package, tuple[str, ...]]] = []  # `require()`, in order
        self._items: list[Spec | EnvSpec | ValueSpec | Library] = []  # registration order is output order
        self._controls: dict[str, str] = {}  # control sequence -> qualname of its declarer
        self._calls: list[type] = []  # components its bodies call, in order (§21a 17)
        self._colours: dict[str, str] = {}  # colour name -> qualname; its own namespace
        self._classes: list[type] = []  # every registered class, in registration order

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
        spec = spec_of(cls, declared_only=self.adopted, whitespace=self.whitespace)
        self._own_library(cls)
        if not self.adopted and cls.defined_by is None:
            render_command(self.prefix, spec)  # lints the body now, so a bad body is refused at import
        control = self._control(spec)
        self._add(spec, (self._controls, control, f"\\{control}"), rendered=cls.defined_by is None)
        cls.__tm_prefix__, cls.__tm_package__, cls.__tm_cs__ = self.prefix, self, control
        self._classes.append(cls)
        return cls

    def _own_library(self, cls: type[Command] | type[Environment]) -> None:
        """The block that defines a component is this package's (`TM-M033`)."""
        if cls.defined_by is not None and cls.defined_by.owner is not self:
            raise DeclarationError(
                f"{cls.__qualname__}: defined_by {cls.defined_by.name!r}, a library of another package",
                code="TM-M033",
                path=cls.__name__,
                hint="declare the component in the package whose library defines it",
            )

    def library(self, name: str, source: str | TemplateRef, *, syntax: Syntax = Syntax.LATEX2E) -> Library:
        """TeX carried into the `.sty` as it is (§21a 12), among the items in registration order: dedented, blank edges
        removed, `%` and `#name` untouched. `Syntax.EXPL3` wraps it in `\\ExplSyntaxOn` / `\\ExplSyntaxOff`. A relative
        `TemplateRef` is relative to the calling module. Name a component's `defined_by` to declare what it defines."""
        if not _LIBRARY_NAME.fullmatch(name):
            raise DeclarationError(
                f"library name {name!r} must match [A-Za-z][A-Za-z0-9_-]*", code="TM-M001", path=name
            )
        if any(isinstance(i, Library) and i.name == name for i in self._items):
            raise DeclarationError(f"library {name!r} is already declared", code="TM-M007", path=name)
        origin = "inline"
        if isinstance(source, TemplateRef):
            source, origin = template_text(source, inspect.stack(0)[1].filename, name), source.path.name
        lib = Library(name, textwrap.dedent(source).strip("\n"), syntax, origin, self)
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
        spec = value_spec_of(cls)
        if self.adopted and not spec.kind.adoptable:
            raise DeclarationError(
                f"{cls.__qualname__}: an adopted package can declare a Value[Text] or Value[Raw] only",
                code="TM-P005",
                path=spec.name,
                hint="declare a length, colour or flag the hand-written package defines as a Command with no arguments",
            )
        if spec.default is None and not self.adopted and not spec.kind.bare:
            raise DeclarationError(f"{cls.__qualname__}: no default", code="TM-M013", path=spec.name)
        tables = {"control": self._controls, "colour": self._colours}
        claims = [
            (tables[table], key, shown) for table, key, shown in spec.kind.claims(self.prefix, spec.name, spec.alias)
        ]
        self._add(spec, *claims)
        cls.__tm_prefix__ = self.prefix
        self._classes.append(cls)
        return cls

    @property
    def registered(self) -> tuple[type, ...]:
        """Every registered command, environment and value class, in registration order."""
        return tuple(self._classes)

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
        """The other packages this one requires or whose components its bodies call (§21a 17), in first-use order."""
        called = (typing.cast("Package", t.__tm_package__) for t in self._calls)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        found = (*(p for p, _ in self._requires), *called)
        return tuple(dict.fromkeys(p for p in found if p is not self and not p.builtin))

    def require_entries(self) -> list[tuple[str, tuple[str, ...]]]:
        """What the `.sty` loads: `require()`d packages in order with their options, then, sorted, the packages the
        values need (M14) and the components call that are not already loaded; computed, never collected by mutation."""
        explicit = [(p.name, o) for p, o in self._requires]
        needs = {p for s in self._items if isinstance(s, ValueSpec) for p in s.needs}
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
        """The `.sty` as lines with provenance (§21a 11): `header`, `requires`, then one path per component or value
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
        for s in self._items:
            if isinstance(s, Spec):
                check_references(self.prefix, s, s.body, self._controls)
            elif isinstance(s, EnvSpec):
                check_references(self.prefix, s, s.begin + "\n" + s.end, self._controls)
        head = header_lines(self.name, self.version, self.date, self.description, stamp(version or generator_version()))
        requires = require_lines(self.require_entries())
        lines = [
            *(Line("header", tex) for tex in head),
            Line("requires", ""),
            *(Line("requires", tex) for tex in requires),
            *([Line("requires", "")] if requires else []),
        ]
        if not self._items:
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
        `\\newcommand`, `\\providecommand`, `\\newenvironment` or an xparse `\\NewDocumentCommand` counts as missing.
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
        return out

    def plan(
        self,
        *body: Node,
        settings: Sequence[AnyValue] = (),
        options: Sequence[str] = (),
        preamble: PreambleSlots | None = None,
    ) -> Plan:
        """A complete `.tex` as lines with provenance (D1a, D2, B2): pure, deterministic, no I/O. `settings` set values
        for the whole document.

        Everything wrong is reported at once, as an `ExceptionGroup` of `ValidationError` (E2).
        """
        preamble = preamble or PreambleSlots()
        problems = [v for node in body for v in node.validate()]
        problems += [
            Violation("TM-M015", path, f"\\{word} is not declared by this package", hint="declare it, or fix the name")
            for i, node in enumerate(body)
            for path, passthrough in _passthroughs(node, f"{type(node).__name__}[{i}]")
            for word in undeclared(self.prefix, passthrough.tex.tex, self._controls)
        ]
        problems += [
            Violation(
                "TM-M015",
                f"preamble.{slot}[{i}]",
                f"\\{word} is not declared by this package",
                hint="declare it, or fix the name",
            )
            for slot, i, item in preamble.items()
            for word in undeclared(self.prefix, tex_of(item).tex, self._controls)
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
            if not _OPTION.fullmatch(o)
        ]
        if problems:
            raise ExceptionGroup("invalid document", [v.error() for v in problems])
        opts = f"[{','.join(options)}]" if options else ""

        def slot(name: str) -> list[Line]:
            return [
                Line(f"preamble.{name}[{i}]", tex)
                for i, raw in enumerate(getattr(preamble, name))
                for tex in tex_of(raw).tex.splitlines()
            ]

        def values(text: bool) -> list[Line]:
            """Text settings go before `\\begin{document}`, where a package reads them; the others go in the body."""
            return [
                Line(
                    f"settings[{i}]",
                    type(v).__tm_kind__.setting(type(v).__tm_prefix__, type(v).__name__, v.value, type(v).colour_name),
                )
                for i, v in enumerate(settings)
                if isinstance(v.value, str | Raw) == text
            ]

        return Plan(
            (
                Line("header", f"% {self.name} document -- {stamp(generator_version())}. Do not edit."),
                *slot("before_class"),
                Line("document", f"\\documentclass{opts}{{{self.document_class}}}"),
                *slot("before_package"),
                *([] if self.builtin else [Line("document", f"\\usepackage{{{self.name}}}")]),
                *values(text=True),
                *slot("after_package"),
                Line("document", "\\begin{document}"),
                *values(text=False),
                *(line for i, node in enumerate(body) for line in node_lines(node, f"{type(node).__name__}[{i}]")),
                Line("document", "\\end{document}"),
            )
        )

    def document(
        self,
        *body: Node,
        settings: Sequence[AnyValue] = (),
        options: Sequence[str] = (),
        preamble: PreambleSlots | None = None,
    ) -> str:
        """The `.tex` text of `plan(...)`."""
        return self.plan(*body, settings=settings, options=options, preamble=preamble).text

    def test_document(
        self,
        *body: Node,
        stub: Sequence[Component] = (),
        settings: Sequence[AnyValue] = (),
        options: Sequence[str] = (),
        preamble: PreambleSlots | None = None,
    ) -> str:
        """A `.tex` for testing `body` against stubs (§21a 20): the real packages are loaded, then each class in `stub`
        is replaced by a macro that writes `texmodel:probe:callN=...` to the log instead of typesetting. Read the calls
        with `texmodel_build.testkit.run_probes` and `testing.Call.parse`; `testing.expand` gives the same calls
        without TeX."""
        slots = preamble or PreambleSlots()
        stubs = dataclasses.replace(slots, after_package=(*slots.after_package, Raw(stub_tex(stub))))
        return self.document(*body, settings=settings, options=options, preamble=stubs)

    def files(self, *, version: str | None = None) -> dict[str, str]:
        """Every generated file, by path relative to the output directory; an adopted package generates none."""
        return {} if self.adopted else {f"{self.name}.sty": self.render(version=version)}
