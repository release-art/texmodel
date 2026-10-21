"""`[tool.texmodel]` in pyproject.toml: the one configuration source (U0)."""

import dataclasses
import pathlib
import tomllib
from typing import Any

from .errors import DeclarationError


@dataclasses.dataclass(frozen=True, kw_only=True)
class Target:
    """A named build (C10): `[tool.texmodel.targets.<name>]`. `variant` and `profile` are carried for later layers."""

    name: str
    source: str
    engine: str = "lualatex"
    variant: str = ""
    profile: str = ""  # verifier profile (A2)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Config:
    prefix: str
    engine: str = "lualatex"
    image: str = ""
    targets: dict[str, Target] = dataclasses.field(default_factory=dict[str, Target])


def load_config(pyproject: pathlib.Path) -> Config:
    """Read and strictly validate `[tool.texmodel]`; unknown keys are refused."""
    table: dict[str, Any] | None = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {}).get("texmodel")
    if table is None:
        raise DeclarationError(f"{pyproject}: no [tool.texmodel] table", code="TM-D001", hint="add [tool.texmodel]")
    known = {f.name for f in dataclasses.fields(Config)}
    if unknown := sorted(set(table) - known):
        raise DeclarationError(
            f"unknown [tool.texmodel] keys: {unknown}", code="TM-D002", hint=f"known: {sorted(known)}"
        )
    try:
        targets = {name: Target(name=name, **body) for name, body in table.pop("targets", {}).items()}
        return Config(**table, targets=targets)
    except TypeError as exc:
        raise DeclarationError(f"[tool.texmodel]: {exc}", code="TM-D003") from exc
