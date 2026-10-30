"""`[tool.texmodel.run]` in pyproject.toml: how to compile and verify (the harness's own table)."""

import dataclasses
import pathlib
import tomllib
from typing import Any

from texmodel.errors import DeclarationError

from .diagnostics import Measure
from .verify import Profile


@dataclasses.dataclass(frozen=True, kw_only=True)
class Target:
    """A named build (C10): `[tool.texmodel.run.targets.<name>]`."""

    name: str
    source: str
    engine: str = "lualatex"
    plan: str = ""  # pointer to the `Plan` behind `source`: diagnostics then name the component (B1)


@dataclasses.dataclass(frozen=True, kw_only=True)
class BuildConfig:
    engine: str = "lualatex"
    image: str = ""  # run in this image; empty runs on the host (e.g. already inside the image)
    targets: dict[str, Target] = dataclasses.field(default_factory=dict[str, Target])
    profiles: dict[str, Profile] = dataclasses.field(default_factory=dict[str, Profile])
    measures: dict[str, Measure] = dataclasses.field(default_factory=dict[str, Measure])
    exempt: dict[str, str] = dataclasses.field(default_factory=dict[str, str])  # glob -> reason (V5)


def load_build_config(pyproject: pathlib.Path) -> BuildConfig:
    """Read and strictly validate `[tool.texmodel.run]`; unknown keys are refused."""
    table: dict[str, Any] | None = (
        tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {}).get("texmodel", {}).get("run")
    )
    if table is None:
        raise DeclarationError(
            f"{pyproject}: no [tool.texmodel.run] table", code="TM-D001", hint="add [tool.texmodel.run]"
        )
    known = {f.name for f in dataclasses.fields(BuildConfig)}
    if unknown := sorted(set(table) - known):
        raise DeclarationError(
            f"unknown [tool.texmodel.run] keys: {unknown}", code="TM-D002", hint=f"known: {sorted(known)}"
        )
    try:
        targets = {name: Target(name=name, **body) for name, body in table.pop("targets", {}).items()}
        profiles = {name: _profile(name, body) for name, body in table.pop("profiles", {}).items()}
        measures = {name: Measure.declare(name, **body) for name, body in table.pop("measures", {}).items()}
        return BuildConfig(**table, targets=targets, profiles=profiles, measures=measures)
    except TypeError as exc:
        raise DeclarationError(f"[tool.texmodel.run]: {exc}", code="TM-D003") from exc


def _profile(name: str, body: dict[str, Any]) -> Profile:
    return Profile(name=name, checks=tuple(body.get("checks", ())), options=body.get("options", {}))


__all__ = ["BuildConfig", "Target", "load_build_config"]
