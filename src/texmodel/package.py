"""A `Package` is the container: its commands render to one `.sty` (G1), deterministically."""

import importlib.metadata
import re
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
)
from .components import Command, Environment, Node, Value, env_spec_of, spec_of, value_spec_of
from .drift import stamp
from .errors import DeclarationError, Violation
from .types import Colour, Length

_NAME = re.compile(r"[a-z][a-z0-9-]*")
_PREFIX = re.compile(r"[a-z]+")
_OPTION = re.compile(r"[A-Za-z0-9][A-Za-z0-9=.-]*")  # a class option is TeX, so it is not free text
_DATE = re.compile(r"\d{4}/\d{2}/\d{2}")  # \ProvidesPackage's date slot: YYYY/MM/DD (G3)


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
        self._items: list[Spec | EnvSpec | ValueSpec] = []  # registration order is output order
        self._controls: dict[str, str] = {}  # control sequence -> qualname of its declarer
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

    def command[C: type[Command]](self, cls: C) -> C:
        """Register a command class."""
        spec = spec_of(cls)
        render_command(self.prefix, spec)  # lints the body now, so a bad body is refused at import
        control = self.prefix + spec.name
        self._add(spec, (self._controls, control, f"\\{control}"))
        cls.__tm_prefix__ = self.prefix
        return cls

    def environment[E: type[Environment]](self, cls: E) -> E:
        """Register an environment class: `\\newenvironment` with its begin and end bodies."""
        spec = env_spec_of(cls)
        render_environment(self.prefix, spec)  # lints both bodies now
        control = self.prefix + spec.name
        self._add(spec, (self._controls, control, f"\\{control}"))
        cls.__tm_prefix__ = self.prefix
        return cls

    def value[V: type[Value[Length] | Value[Colour] | Value[bool]]](self, cls: V) -> V:
        """Register a value class: `\\newlength`, `\\definecolor` or `\\newif` by its type (M1a)."""
        spec = value_spec_of(cls)
        control = self.prefix + spec.name
        if isinstance(spec.default, Length):
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
    def required_packages(self) -> tuple[str, ...]:
        """The union of what the components declare, sorted (M14); computed, never collected by mutation."""
        return tuple(sorted({p for s in self._items if isinstance(s, ValueSpec) for p in s.needs}))

    def render(self, *, version: str | None = None) -> str:
        """The `.sty` text. `version` is the generator's, recorded in the header; default the installed texmodel's.

        Body references are checked here, not at registration: a body may name a component declared after it, so the
        family is only complete once someone asks for output (`files()` and `texmodel check` both do) (M8, G2).
        """
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

    def document(
        self,
        *body: Node,
        settings: Sequence[Value[Length] | Value[Colour] | Value[bool]] = (),
        options: Sequence[str] = (),
    ) -> str:
        """A complete `.tex` (D1a, D2): pure, deterministic, no I/O. `settings` set values for the whole document.

        Everything wrong is reported at once, as an `ExceptionGroup` of `ValidationError` (E2).
        """
        problems = [v for node in body for v in node.validate()]
        problems += [
            Violation("TM-C006", f"options[{i}]", f"class option {o!r} must match [A-Za-z0-9][A-Za-z0-9=.-]*")
            for i, o in enumerate(options)
            if not _OPTION.fullmatch(o)
        ]
        if problems:
            raise ExceptionGroup("invalid document", [v.error() for v in problems])
        opts = f"[{','.join(options)}]" if options else ""
        return "\n".join(
            [
                f"% {self.name} document -- {stamp(generator_version())}. Do not edit.",
                f"\\documentclass{opts}{{{self.document_class}}}",
                f"\\usepackage{{{self.name}}}",
                "\\begin{document}",
                *(setting(type(v).__tm_prefix__, type(v).__name__, v.value) for v in settings),
                *(node.render() for node in body),
                "\\end{document}",
                "",
            ]
        )

    def files(self, *, version: str | None = None) -> dict[str, str]:
        """Every generated file, by path relative to the output directory."""
        return {f"{self.name}.sty": self.render(version=version)}
