"""A `Package` is the container: its commands render to one `.sty` (G1), deterministically."""

import importlib.metadata
import re

from ._internal.render import (
    Spec,
    ValueSpec,
    bool_names,
    check_references,
    colour_name,
    render_command,
    render_package,
    render_value,
)
from .components import Command, Value, spec_of, value_spec_of
from .drift import stamp
from .errors import DeclarationError
from .types import Colour, Length

_NAME = re.compile(r"[a-z][a-z0-9-]*")
_PREFIX = re.compile(r"[a-z]+")
_DATE = re.compile(r"\d{4}/\d{2}/\d{2}")  # \ProvidesPackage's date slot: YYYY/MM/DD (G3)


def generator_version() -> str:
    """`X.Y.Z` of the installed texmodel, without dev or local parts, so output does not churn per commit (G7)."""
    m = re.match(r"\d+\.\d+\.\d+", importlib.metadata.version("texmodel"))
    return m[0] if m else "0.0.0"


class Package:
    def __init__(
        self, name: str, *, prefix: str, version: str = "0.0.0", date: str = "1970/01/01", description: str = ""
    ) -> None:
        if not _NAME.fullmatch(name):
            raise DeclarationError(f"package name {name!r} must match [a-z][a-z0-9-]*", code="TM-P001")
        if not _PREFIX.fullmatch(prefix):
            raise DeclarationError(f"prefix {prefix!r} must be lowercase letters", code="TM-P002")
        if not _DATE.fullmatch(date):
            raise DeclarationError(f"date {date!r} must be YYYY/MM/DD (\\ProvidesPackage's date slot)", code="TM-P003")
        self.name, self.prefix, self.version, self.date, self.description = name, prefix, version, date, description
        self._items: list[Spec | ValueSpec] = []  # registration order is output order
        self._controls: dict[str, str] = {}  # control sequence -> qualname of its declarer
        self._colours: dict[str, str] = {}  # colour name -> qualname; its own namespace

    def _add(self, spec: Spec | ValueSpec, *claims: tuple[dict[str, str], str, str]) -> None:
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
                check_references(self.prefix, s, self._controls)
        body = "\n\n".join(
            render_value(self.prefix, s) if isinstance(s, ValueSpec) else render_command(self.prefix, s)
            for s in self._items
        )
        return render_package(
            self.name,
            self.version,
            self.date,
            self.description,
            stamp(version or generator_version()),
            self.required_packages,
            body,
        )

    def files(self, *, version: str | None = None) -> dict[str, str]:
        """Every generated file, by path relative to the output directory."""
        return {f"{self.name}.sty": self.render(version=version)}
