"""A `Package` is the container: its commands render to one `.sty` (G1), deterministically.

An adopted package (M9) is the other way round: the `.sty` is hand-written, the components only declare its interface,
and `check_interface` compares the two.
"""

import dataclasses
import importlib.metadata
import re
import typing
from collections.abc import Sequence

from ._internal.render import (
    EnvSpec,
    Spec,
    ValueSpec,
    bool_names,
    check_references,
    colour_name,
    render_command,
    render_environment,
    render_package,
    render_value,
    setting,
    signature,
    undeclared,
)
from ._internal.scan import scan_declarations
from .body import Whitespace
from .components import Command, Environment, Node, Value, env_spec_of, spec_of, value_spec_of
from .drift import stamp
from .errors import DeclarationError, Violation
from .plan import Line, Plan, node_lines
from .types import Colour, Length, Raw, Text

_NAME = re.compile(r"[a-z][a-z0-9-]*")
_PREFIX = re.compile(r"[a-z]+")
_OPTION = re.compile(r"[A-Za-z0-9][A-Za-z0-9=.-]*")  # a class option is TeX, so it is not free text
_DATE = re.compile(r"\d{4}/\d{2}/\d{2}")  # \ProvidesPackage's date slot: YYYY/MM/DD (G3)


@dataclasses.dataclass(frozen=True)
class PreambleSlots:
    """TeX a document places around its class and package lines (D3), each slot a tuple of `Raw` in order.

    `before_class` is where `\\DocumentMetadata` must go; `before_package` is for what the package needs when it
    loads (`\\input@path`, package options); `after_package` is for what needs it loaded (`\\graphicspath`,
    per-document `\\renewcommand`s). Public names of the package used here must be declared (M8).
    """

    before_class: tuple[Raw, ...] = ()
    before_package: tuple[Raw, ...] = ()
    after_package: tuple[Raw, ...] = ()


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
        whitespace: Whitespace = Whitespace.KEEP,
    ) -> None:
        if not _NAME.fullmatch(name):
            raise DeclarationError(f"package name {name!r} must match [a-z][a-z0-9-]*", code="TM-P001")
        if not _PREFIX.fullmatch(prefix):
            raise DeclarationError(f"prefix {prefix!r} must be lowercase letters", code="TM-P002")
        if not _DATE.fullmatch(date):
            raise DeclarationError(f"date {date!r} must be YYYY/MM/DD (\\ProvidesPackage's date slot)", code="TM-P003")
        if not _NAME.fullmatch(document_class):
            raise DeclarationError(f"document class {document_class!r} must match [a-z][a-z0-9-]*", code="TM-P004")
        self.name, self.prefix, self.version, self.date, self.description = name, prefix, version, date, description
        self.document_class = document_class
        self.whitespace = whitespace  # the policy of a body piece that names none (M8)
        self.adopted = adopted  # the `.sty` is hand-written; components only declare it (M9)
        self._items: list[Spec | EnvSpec | ValueSpec] = []  # registration order is output order
        self._controls: dict[str, str] = {}  # control sequence -> qualname of its declarer
        self._calls: list[type] = []  # components its bodies call, in order (§21a 17)
        self._colours: dict[str, str] = {}  # colour name -> qualname; its own namespace

    def _add(self, spec: Spec | EnvSpec | ValueSpec, *claims: tuple[dict[str, str], str, str]) -> None:
        """Claim names (table, key, how to show it); a collision is an error here, not at \\begin{document} (M7)."""
        for table, key, shown in claims:
            if key in table:
                raise DeclarationError(
                    f"{spec.qualname}: {shown} is already declared by {table[key]}", code="TM-M007", path=spec.name
                )
        for table, key, _ in claims:
            table[key] = spec.qualname
        self._items.append(spec)
        if not isinstance(spec, ValueSpec):
            self._calls.extend(spec.refs)

    def command[C: type[Command]](self, cls: C) -> C:
        """Register a command class."""
        spec = spec_of(cls, declared_only=self.adopted, whitespace=self.whitespace)
        if not self.adopted:
            render_command(self.prefix, spec)  # lints the body now, so a bad body is refused at import
        control = self.prefix + spec.name
        self._add(spec, (self._controls, control, f"\\{control}"))
        cls.__tm_prefix__, cls.__tm_package__ = self.prefix, self
        return cls

    def environment[E: type[Environment]](self, cls: E) -> E:
        """Register an environment class: `\\newenvironment` with its begin and end bodies."""
        spec = env_spec_of(cls, declared_only=self.adopted, whitespace=self.whitespace)
        if not self.adopted:
            render_environment(self.prefix, spec)  # lints both bodies now
        control = self.prefix + spec.name
        self._add(spec, (self._controls, control, f"\\{control}"))
        cls.__tm_prefix__, cls.__tm_package__ = self.prefix, self
        return cls

    def value[V: type[Value[Length] | Value[Colour] | Value[bool] | Value[Text]]](self, cls: V) -> V:
        """Register a value class: `\\newlength`, `\\definecolor`, `\\newif` or `\\newcommand` by its type (M1a)."""
        spec = value_spec_of(cls)
        if self.adopted and spec.kind != "Text":
            raise DeclarationError(
                f"{cls.__qualname__}: an adopted package can declare a Value[Text] only",
                code="TM-P005",
                path=spec.name,
                hint="declare a length, colour or flag the hand-written package defines as a Command with no arguments",
            )
        if spec.default is None and not self.adopted:
            raise DeclarationError(f"{cls.__qualname__}: no default", code="TM-M013", path=spec.name)
        control = self.prefix + spec.name
        if isinstance(spec.default, Length | str | None):
            claims = [(self._controls, control, f"\\{control}")]
        elif isinstance(spec.default, bool):
            claims = [(self._controls, c, f"\\{c}") for c in (control, *bool_names(self.prefix, spec.name))]
        else:
            name = colour_name(self.prefix, spec.name)
            claims = [(self._colours, name, f"colour {name}")]
        self._add(spec, *claims)
        cls.__tm_prefix__ = self.prefix
        return cls

    @property
    def depends_on(self) -> tuple["Package", ...]:
        """The other packages whose components its bodies call, in first-use order (§21a 17)."""
        found = (typing.cast("Package", t.__tm_package__) for t in self._calls)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        return tuple(dict.fromkeys(p for p in found if p is not self))

    @property
    def required_packages(self) -> tuple[str, ...]:
        """The union of what the components declare (M14) and the packages they call, sorted; computed, never
        collected by mutation."""
        needs = {p for s in self._items if isinstance(s, ValueSpec) for p in s.needs}
        return tuple(sorted({*needs, *(p.name for p in self.depends_on)}))

    def _check_cycles(self, path: tuple["Package", ...] = ()) -> None:
        """A package that (through others) requires itself cannot load (`TM-P007`)."""
        if self in path:
            chain = " -> ".join(p.name for p in (*path[path.index(self) :], self))
            raise DeclarationError(f"packages require each other: {chain}", code="TM-P007", path=self.name)
        for dependency in self.depends_on:
            dependency._check_cycles((*path, self))  # noqa: SLF001

    def render(self, *, version: str | None = None) -> str:
        """The `.sty` text. `version` is the generator's, recorded in the header; default the installed texmodel's.

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
        body = "\n\n".join(self._render_item(s) for s in self._items)
        return render_package(
            self.name,
            self.version,
            self.date,
            self.description,
            stamp(version or generator_version()),
            self.required_packages,
            body,
        )

    def _render_item(self, s: Spec | EnvSpec | ValueSpec) -> str:
        if isinstance(s, ValueSpec):
            return render_value(self.prefix, s)
        return render_command(self.prefix, s) if isinstance(s, Spec) else render_environment(self.prefix, s)

    def check_interface(self, *sources: str) -> list[Violation]:
        """Every declared component is defined in `sources` (the hand-written TeX) with the signature declared (M9).

        Read by `texmodel check` for an adopted package. A name that `sources` define some other way than
        `\\newcommand`, `\\providecommand` or `\\newenvironment` counts as missing.
        """
        found = scan_declarations("\n".join(sources), self.prefix)
        out: list[Violation] = []
        for s in self._items:
            control, want = self.prefix + s.name, "" if isinstance(s, ValueSpec) else signature(s.args)
            if control not in found:
                out.append(Violation("TM-C010", s.name, f"\\{control} is declared but the sources do not define it"))
            elif found[control] != want:
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
        settings: Sequence[Value[Length] | Value[Colour] | Value[bool] | Value[Text]] = (),
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
            Violation(
                "TM-M015",
                f"preamble.{slot}[{i}]",
                f"\\{word} is not declared by this package",
                hint="declare it, or fix the name",
            )
            for slot in ("before_class", "before_package", "after_package")
            for i, raw in enumerate(getattr(preamble, slot))
            for word in undeclared(self.prefix, raw.tex, self._controls)
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
                for tex in raw.tex.splitlines()
            ]

        def values(text: bool) -> list[Line]:
            """Text settings go before `\\begin{document}`, where a package reads them; the others go in the body."""
            return [
                Line(f"settings[{i}]", setting(type(v).__tm_prefix__, type(v).__name__, v.value))
                for i, v in enumerate(settings)
                if isinstance(v.value, str) == text
            ]

        return Plan(
            (
                Line("header", f"% {self.name} document -- {stamp(generator_version())}. Do not edit."),
                *slot("before_class"),
                Line("document", f"\\documentclass{opts}{{{self.document_class}}}"),
                *slot("before_package"),
                Line("document", f"\\usepackage{{{self.name}}}"),
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
        settings: Sequence[Value[Length] | Value[Colour] | Value[bool] | Value[Text]] = (),
        options: Sequence[str] = (),
        preamble: PreambleSlots | None = None,
    ) -> str:
        """The `.tex` text of `plan(...)`."""
        return self.plan(*body, settings=settings, options=options, preamble=preamble).text

    def files(self, *, version: str | None = None) -> dict[str, str]:
        """Every generated file, by path relative to the output directory; an adopted package generates none."""
        return {} if self.adopted else {f"{self.name}.sty": self.render(version=version)}
