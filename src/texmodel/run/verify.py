"""Verifier plugins (V4, V5, L1): checks over a built file, discovered through entry points.

A verifier is any object with a `name`, an `unavailable(options)` that says why it cannot run here (or `None`), and a
`async verify(path, options)` returning findings. Register it in the `texmodel.run.verifiers` entry-point group, as a
callable that returns the verifier.

The rule that matters is V5, **unconfirmable means failure**: a verifier that cannot run, a file that cannot be opened,
a plugin that crashes, and a profile that selects nothing are all errors, never skips. The only way to excuse a file is
the exemption registry, which keeps it listed with its reason.
"""

import asyncio
import dataclasses
import fnmatch
import importlib.metadata
import pathlib
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .diagnostics import Severity
from .errors import ToolchainError

GROUP = "texmodel.run.verifiers"


@dataclasses.dataclass(frozen=True)
class Finding:
    """One issue a check raised, optionally tied to a 1-based page."""

    check: str
    severity: Severity
    message: str
    page: int | None = None


@dataclasses.dataclass(frozen=True, kw_only=True)
class Profile:
    """Which verifiers to run (empty: every registered one) and their options, keyed by verifier name."""

    name: str = "default"
    checks: tuple[str, ...] = ()
    options: Mapping[str, Mapping[str, Any]] = dataclasses.field(default_factory=dict[str, Mapping[str, Any]])


@dataclasses.dataclass(frozen=True)
class FileReport:
    path: pathlib.Path
    findings: tuple[Finding, ...] = ()
    exempt: str | None = None  # why the file was declared out of scope; listed, never a failure

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.ERROR)

    @property
    def ok(self) -> bool:
        return not self.errors


class Verifier(Protocol):
    name: str

    def unavailable(self, options: Mapping[str, Any]) -> str | None:
        """Why this verifier cannot run here with these options (a missing tool, say), or `None`."""
        ...

    async def verify(self, path: pathlib.Path, options: Mapping[str, Any]) -> Sequence[Finding]: ...


def registered() -> dict[str, Verifier]:
    """Every verifier in the entry-point group. A plugin that fails to load is an error, not a silent omission."""
    found: dict[str, Verifier] = {}
    for entry in importlib.metadata.entry_points(group=GROUP):
        try:
            verifier: Verifier = entry.load()()
        except Exception as exc:
            raise ToolchainError(
                f"verifier plugin {entry.name!r} failed to load: {exc!r}", code="TM-V001", hint="reinstall the plugin"
            ) from exc
        found[verifier.name] = verifier
    return found


def exemption(path: pathlib.PurePath, exempt: Mapping[str, str]) -> str | None:
    """The reason `path` is exempt: a glob matching the path or any trailing part of it (`res/**`, `*_preview.pdf`)."""
    parts = path.as_posix().split("/")
    tails = ["/".join(parts[i:]) for i in range(len(parts))]
    for glob, reason in exempt.items():
        if any(fnmatch.fnmatch(tail, glob) for tail in tails):
            return reason
    return None


async def verify_file(
    path: pathlib.Path,
    profile: Profile,
    available: Mapping[str, Verifier],
    exempt: Mapping[str, str] | None = None,
) -> FileReport:
    """Run the profile's verifiers over one file. Reports; never raises for a bad file or a bad plugin."""
    if reason := exemption(path, exempt or {}):
        return FileReport(path, exempt=reason)
    names = profile.checks or tuple(available)
    if not names:
        return FileReport(
            path, (Finding("verify", Severity.ERROR, "no verifier selected or installed: nothing was checked"),)
        )
    if not path.is_file():
        return FileReport(path, (Finding("open", Severity.ERROR, "no such file"),))
    findings: list[Finding] = []
    for name in names:
        verifier = available.get(name)
        if verifier is None:
            findings.append(Finding(name, Severity.ERROR, f"unknown verifier; installed: {sorted(available)}"))
            continue
        options = profile.options.get(name, {})
        if why := verifier.unavailable(options):
            findings.append(Finding(name, Severity.ERROR, f"cannot confirm: {why}"))
            continue
        try:
            findings.extend(await verifier.verify(path, options))
        except Exception as exc:
            findings.append(Finding(name, Severity.ERROR, f"verifier crashed: {exc!r}"))
    return FileReport(path, tuple(findings))


async def verify_files(
    paths: Sequence[pathlib.Path],
    profile: Profile,
    available: Mapping[str, Verifier],
    exempt: Mapping[str, str] | None = None,
    *,
    jobs: int = 1,
) -> list[FileReport]:
    """One report per path, in order, up to `jobs` at once."""
    slots = asyncio.Semaphore(max(1, jobs))

    async def one(path: pathlib.Path) -> FileReport:
        async with slots:
            return await verify_file(path, profile, available, exempt)

    async with asyncio.TaskGroup() as group:
        running = [group.create_task(one(p)) for p in paths]
    return [r.result() for r in running]


def expand_targets(
    paths: Sequence[pathlib.Path], exclude: Sequence[str] = (), suffix: str = ".pdf"
) -> list[pathlib.Path]:
    """Files as given; a directory expands to every `suffix` file beneath it minus `exclude` globs (relative to it)."""
    out: list[pathlib.Path] = []
    for path in paths:
        if path.is_dir():
            out += [
                p
                for p in sorted(path.rglob(f"*{suffix}"))
                if exemption(p.relative_to(path), dict.fromkeys(exclude, "")) is None
            ]
        else:
            out.append(path)
    return out


__all__ = [
    "FileReport",
    "Finding",
    "GROUP",
    "Profile",
    "Verifier",
    "exemption",
    "expand_targets",
    "registered",
    "verify_file",
    "verify_files",
]
