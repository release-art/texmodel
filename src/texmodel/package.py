"""A `Package` is the container: its commands render to one `.sty` (G1), deterministically."""

import importlib.metadata
import re

from ._internal.render import Spec, render_command, render_package
from .components import Command, spec_of
from .drift import stamp
from .errors import DeclarationError

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
        self._specs: dict[str, Spec] = {}

    def command[C: type[Command]](self, cls: C) -> C:
        """Register a command class; a name collision is an error here, not at \\begin{document} (M7)."""
        spec = spec_of(cls)
        control = self.prefix + spec.name
        if control in self._specs:
            raise DeclarationError(
                f"{spec.qualname}: \\{control} is already declared by {self._specs[control].qualname}",
                code="TM-M007",
                path=spec.name,
            )
        render_command(self.prefix, spec)  # lints the body now, so a bad body is refused at import
        self._specs[control] = spec
        return cls

    def render(self, *, version: str | None = None) -> str:
        """The `.sty` text. `version` is the generator's, recorded in the header; default the installed texmodel's."""
        commands = "\n\n".join(render_command(self.prefix, s) for s in self._specs.values())
        return render_package(
            self.name, self.version, self.date, self.description, stamp(version or generator_version()), commands
        )

    def files(self, *, version: str | None = None) -> dict[str, str]:
        """Every generated file, by path relative to the output directory."""
        return {f"{self.name}.sty": self.render(version=version)}
