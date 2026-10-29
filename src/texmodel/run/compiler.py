"""A thin compiler (C1): runs `latexmk` over a `.tex` and returns a typed `CompileResult`.

It starts processes only through `_internal.spawn`, the one module allowed to (import-linter). Argv lists only (never a
shell string), shell escape off, intermediates out of tree (C7), `latexmk` as the single rerun strategy. Reproducibility
is the image's job: with an `image` the compile runs `docker run` over it with the sources mounted read-only and the
output directory writable; without one it runs the tools on this machine (for instance, when already inside the image).
"""

import asyncio
import dataclasses
import logging
import os
import pathlib
import re
import time
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from texmodel.errors import DeclarationError
from texmodel.plan import Plan

from ._internal.converge import aux_diff
from ._internal.env import build_env
from ._internal.logparse import page_count
from ._internal.spawn import Proc, spawn
from ._internal.styscan import SAFE_NAME
from .diagnostics import Diagnostic, Measure, NotConverged, Severity, Unexplained
from .engines import LUALATEX, Engine
from .errors import ToolchainError
from .result import CompileResult

logger = logging.getLogger(__name__)

_RUN = re.compile(r"Run number (\d+) of rule")
# latexmk found nothing out of date and ran no pass: the outputs from an earlier run are current.
_UP_TO_DATE = re.compile(r"All targets \(.*\) are up-to-date|Nothing to do")
_UNSTABLE = re.compile(r"Maximum runs of .+ reached without getting stable files")
_VERSION = re.compile(r"Version (\S+)")
_INTERMEDIATE = ("aux", "log", "fls", "fdb_latexmk", "out", "toc", "lof", "lot", "bbl", "blg", "idx", "ind", "ilg",
                 "synctex.gz", "run.xml", "bcf", "nav", "snm", "vrb")  # fmt: skip
_TOOLS = ("kpsewhich", "gs", "verapdf")  # probed besides the engine and latexmk, to report capability gaps
_REFERENCE_PATHS = {"src": "/work/src", "out": "/work/out", "cache": "/cache"}
_TAIL = 8


@dataclasses.dataclass(frozen=True)
class Versions:
    engine_version: str
    latexmk_version: str
    tools: tuple[str, ...]  # of kpsewhich, gs, verapdf: those present


@dataclasses.dataclass(frozen=True)
class ImageInfo:
    digest: str
    revision: str


def _located(diagnostic: Diagnostic, plans: Mapping[str, Plan]) -> Diagnostic:
    """Add the path of the plan of the diagnostic's file, by file name, for its line. A line whose file the log does
    not say is not placed: a guess at the main document would name the wrong component."""
    if diagnostic.file is None or diagnostic.line is None:
        return diagnostic
    plan = plans.get(pathlib.PurePath(diagnostic.file).name)
    if plan is None or not 1 <= diagnostic.line <= len(plan.lines):
        return diagnostic
    return dataclasses.replace(diagnostic, path=plan.path_of(diagnostic.line))


def _tail(text: str) -> str:
    return " | ".join(text.strip().splitlines()[-_TAIL:])


@dataclasses.dataclass(frozen=True, kw_only=True)
class Compiler:
    """Compile settings in one place. `image=None` runs on this machine; a tag runs in that image."""

    engine: Engine = LUALATEX
    image: str | None = None
    roots: tuple[pathlib.Path, ...] = ()  # ordered asset roots, earlier wins (C4)
    font_dirs: tuple[pathlib.Path, ...] = ()  # found by family name (OSFONTDIR), not by path
    halt_on_error: bool = False  # stop at the first error; the default reports every one
    font_cache: pathlib.Path | None = None  # persistent luaotfload cache; without it every container run rebuilds it
    max_passes: int = 5
    epoch: int | None = None  # reproducible mode (C6): pins SOURCE_DATE_EPOCH
    measures: tuple[Measure, ...] = ()  # how to read a package's warnings as typed measurements (B2)
    timeout: float = 300.0  # seconds, wall clock; the container is killed when it passes
    # what a probe found, kept for this compiler's life; `dataclasses.replace` starts a new one, as a new engine needs
    _probed: dict[str, Any] = dataclasses.field(default_factory=dict[str, Any], init=False, repr=False, compare=False)

    async def _fonts(self) -> pathlib.Path | None:
        """The font cache, one directory per image: a font database is only valid for the fonts it indexed."""
        if self.font_cache is None:
            return None
        info = await self.image_info()
        return (self.font_cache / info.digest.removeprefix("sha256:")[:12] if info else self.font_cache).resolve()

    # -- probing -----------------------------------------------------------------------------------------

    async def versions(self) -> Versions:
        """The engine's and latexmk's versions and the optional tools present, probed once."""
        if "versions" in self._probed:
            return self._probed["versions"]
        script = (
            f"latexmk -v 2>&1 | head -n 2; echo @@; {self.engine.binary} --version 2>&1 | head -n 1; echo @@; "
            f"for t in {' '.join(_TOOLS)}; do command -v $t >/dev/null && echo $t; done; true"
        )
        proc = await self._sh(script)
        latexmk, engine, tools = (proc.stdout.split("@@\n") + ["", ""])[:3]
        m = _VERSION.search(latexmk)
        found = self._probed["versions"] = Versions(engine.strip(), m[1] if m else "", tuple(tools.split()))
        return found

    async def image_info(self) -> ImageInfo | None:
        """The image's digest and revision, inspected once; `None` without an image."""
        if self.image is None:
            return None
        if "image" in self._probed:
            return self._probed["image"]
        fmt = '{{.Id}}|{{index .Config.Labels "org.opencontainers.image.revision"}}'
        proc = await spawn(
            ["docker", "image", "inspect", "--format", fmt, self.image], cwd=None, env=self._host_env(), timeout=60
        )
        if proc.returncode != 0:
            raise ToolchainError(
                f"image {self.image} not available: {_tail(proc.stderr)}",
                code="TM-T002",
                hint=f"docker pull {self.image}",
            )
        digest, _, revision = proc.stdout.strip().partition("|")
        found = self._probed["image"] = ImageInfo(digest, revision)
        return found

    async def check_ready(self) -> Versions:
        """The versions, or a ToolchainError naming what is missing (`doctor` and `compile` both use this)."""
        await self.image_info()
        versions = await self.versions()
        if not versions.latexmk_version:
            where = f"image {self.image}" if self.image else "this machine"
            raise ToolchainError(
                f"latexmk is not available in {where}", code="TM-T003", hint="the images need latexmk (plan C8)"
            )
        return versions

    async def missing_files(self, files: Sequence[str]) -> tuple[str, ...]:
        """Which of `files` `kpsewhich` cannot find, here or in the image (D2); no network is used."""
        if not files:
            return ()
        if bad := [f for f in files if not SAFE_NAME.fullmatch(f)]:
            raise DeclarationError(f"not a plain file name: {bad[0]!r}", code="TM-T006", hint="letters, digits . _ -")
        script = (
            "# texmodel:missing\n"
            "command -v kpsewhich >/dev/null || { echo 'kpsewhich is not installed' >&2; exit 127; }\n"
            f'for f in {" ".join(files)}; do kpsewhich "$f" >/dev/null || echo "$f"; done'
        )
        return tuple((await self._sh(script)).stdout.split())

    # -- compiling ---------------------------------------------------------------------------------------

    async def compile(
        self,
        source: pathlib.Path,
        outdir: pathlib.Path,
        *,
        plan: Plan | None = None,
        plans: Mapping[str, Plan] | None = None,
    ) -> CompileResult:
        """Compile `source`. Given the `Plan` that wrote it, each diagnostic located in `source` carries the `path` of
        the component behind its line (C11); `plans` does the same for other files by name (`{"acme.sty": ...}`)."""
        source, outdir = source.resolve(), outdir.resolve()
        if not source.is_file():
            raise DeclarationError(f"{source}: no such file", code="TM-X001")
        if outdir == source.parent or outdir in source.parent.parents:
            raise DeclarationError(
                f"output directory {outdir} is the source directory or contains it",
                code="TM-X002",
                hint="intermediates never share a directory with sources (C7)",
            )
        versions = await self.check_ready()
        info = await self.image_info()
        outdir.mkdir(parents=True, exist_ok=True)
        started = time.time()
        proc = await self._latexmk(source, outdir)
        diagnostics: list[Diagnostic] = []
        stem = source.stem
        log, pdf = outdir / f"{stem}.log", outdir / f"{stem}.pdf"
        current = bool(_UP_TO_DATE.search(proc.stdout))
        fresh = log.is_file() and (current or log.stat().st_mtime >= started - 1)  # not a leftover from a failed run
        text = log.read_text(encoding="utf-8", errors="replace") if fresh else ""
        diagnostics.extend(self.engine.parse_log(text, self.measures))
        pages = page_count(text)
        has_pdf = fresh and pdf.is_file() and pages is not None
        passes = max((int(n) for n in _RUN.findall(proc.stdout)), default=0)

        if _UNSTABLE.search(proc.stdout + proc.stderr):  # latexmk says it on stderr
            diagnostics.append(await self._not_converged(source, outdir, passes))
        if proc.timed_out:
            diagnostics.append(Unexplained(message=f"timed out after {self.timeout:g}s"))
        elif (proc.returncode != 0 or not has_pdf) and not any(d.severity is Severity.ERROR for d in diagnostics):
            tail = _tail(proc.stdout + proc.stderr)
            diagnostics.append(
                Unexplained(message=f"latexmk exited {proc.returncode} with no diagnosable error: {tail}")
            )

        found_plans = {**(plans or {}), **({source.name: plan} if plan is not None else {})}
        diagnostics = [_located(d, found_plans) for d in diagnostics]
        result = CompileResult(
            pdf=pdf if has_pdf else None,
            log=log if fresh else None,
            passes=passes,
            pages=pages,
            diagnostics=tuple(diagnostics),
            seconds=round(time.time() - started, 3),
            engine=self.engine.name,
            engine_version=versions.engine_version,
            latexmk_version=versions.latexmk_version,
            image=self.image,
            image_digest=info.digest if info else None,
            image_revision=info.revision if info else None,
        )
        return result

    async def clean(self, source: pathlib.Path, outdir: pathlib.Path, *, everything: bool = False) -> None:
        """`latexmk -c` (`-C` with `everything`); if latexmk cannot run, delete the known intermediate files."""
        source, outdir = source.resolve(), outdir.resolve()
        try:
            proc = await self._tool(
                "latexmk", ["-C" if everything else "-c", "-outdir={out}", source.name], source, outdir
            )
            if proc.returncode == 0:
                return
        except ToolchainError:
            pass
        logger.info("latexmk could not clean %s; deleting known intermediates", outdir)
        for ext in (*_INTERMEDIATE, *(("pdf",) if everything else ())):
            (outdir / f"{source.stem}.{ext}").unlink(missing_ok=True)

    # -- internals ---------------------------------------------------------------------------------------

    async def _latexmk(self, source: pathlib.Path, outdir: pathlib.Path, extra: Sequence[str] = ()) -> Proc:
        args = [
            *self.engine.latexmk_args,
            "-interaction=nonstopmode",
            "-file-line-error",
            *(["-halt-on-error"] if self.halt_on_error else []),
            "-outdir={out}",
            "-e",
            f"$max_repeat={int(self.max_passes)};",
            *extra,
            source.name,
        ]
        proc = await self._tool("latexmk", args, source, outdir)
        if proc.returncode == 127 or (self.image and proc.returncode == 125):
            # 125 is docker's own failure (the daemon, a mount), not latexmk's: say which, so a one-off is diagnosable
            who = "docker could not start the container" if proc.returncode == 125 else "could not run latexmk"
            raise ToolchainError(f"{who}: {_tail(proc.stderr)}", code="TM-T004", hint="run `texmodel run doctor`")
        return proc

    async def _not_converged(self, source: pathlib.Path, outdir: pathlib.Path, passes: int) -> Diagnostic:
        """One more pass, to see which `.aux` entries still move (C1a)."""
        aux = outdir / f"{source.stem}.aux"
        before = aux.read_text(encoding="utf-8", errors="replace") if aux.is_file() else ""
        await self._latexmk(source, outdir, extra=["-g", "-e", "$max_repeat=1;"])
        after = aux.read_text(encoding="utf-8", errors="replace") if aux.is_file() else ""
        changed = aux_diff(before, after)
        return NotConverged(
            message=f"did not converge in {passes} passes; still changing: {', '.join(changed) or '(nothing in .aux)'}",
            changed=changed,
        )

    async def _locations(self, source: pathlib.Path, outdir: pathlib.Path) -> dict[str, str | list[str]]:
        if self.image:
            roots = [f"/work/roots/{i}" for i, _ in enumerate(self.roots)]
            fonts = [f"/work/fonts/{i}" for i, _ in enumerate(self.font_dirs)]
            return {
                **_REFERENCE_PATHS,
                "roots": roots,
                "fonts": fonts,
                "cache": _REFERENCE_PATHS["cache"] if self.font_cache else "",
            }
        return {
            "src": str(source.parent),
            "out": str(outdir),
            "roots": [str(r.resolve()) for r in self.roots],
            "fonts": [str(f.resolve()) for f in self.font_dirs],
            "cache": str(fonts) if (fonts := await self._fonts()) else "",
        }

    def _env(self, loc: dict[str, str | list[str]]) -> dict[str, str]:
        roots, fonts = loc["roots"], loc["fonts"]
        assert isinstance(roots, list) and isinstance(fonts, list)
        return build_env(roots=roots, fonts=fonts, epoch=self.epoch, cache=str(loc["cache"]) or None)

    def _host_env(self) -> dict[str, str]:
        return {k: os.environ[k] for k in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG") if k in os.environ}

    async def _tool(self, tool: str, args: Sequence[str], source: pathlib.Path, outdir: pathlib.Path) -> Proc:
        """Run `tool` with `{out}` in args replaced by the output directory as the tool sees it. A run in the image that
        times out or is cancelled has its container killed, so none is left behind."""
        loc = await self._locations(source, outdir)
        roots = loc["roots"]
        assert isinstance(roots, list)
        env = self._env(loc)
        argv = [a.replace("{out}", str(loc["out"])) for a in args]
        cache = await self._fonts()
        if cache:
            cache.mkdir(parents=True, exist_ok=True)
        if not self.image:
            return await spawn([tool, *argv], cwd=source.parent, env={**self._host_env(), **env}, timeout=self.timeout)
        name = f"texmodel-{uuid.uuid4().hex[:12]}"
        mounts = [(source.parent, loc["src"], True), (outdir, loc["out"], False)]
        mounts += [(r.resolve(), p, True) for r, p in zip(self.roots, roots, strict=True)]
        fonts = loc["fonts"]
        assert isinstance(fonts, list)
        mounts += [(f.resolve(), p, True) for f, p in zip(self.font_dirs, fonts, strict=True)]
        if cache:
            mounts.append((cache, loc["cache"], False))
        docker = self._docker(name, mounts, env, tool)
        try:
            proc = await spawn([*docker, *argv], cwd=None, env=self._host_env(), timeout=self.timeout)
        except asyncio.CancelledError:
            await self._kill(name)
            raise
        if proc.timed_out:
            await self._kill(name)
        return proc

    async def _kill(self, container: str) -> None:
        """`docker kill`: killing the `docker run` client does not stop its container."""
        await spawn(["docker", "kill", container], cwd=None, env=self._host_env(), timeout=30)

    def _docker(
        self,
        name: str,
        mounts: Sequence[tuple[pathlib.Path, str | list[str], bool]],
        env: dict[str, str],
        entrypoint: str,
    ) -> list[str]:
        assert self.image
        argv = [
            "docker", "run", "--rm", "--name", name, "--user", f"{os.getuid()}:{os.getgid()}", "-w", "/work/src",
        ]  # fmt: skip
        for host, target, readonly in mounts:
            if "," in str(host):
                raise DeclarationError(f"{host}: a comma in a mounted path is not supported", code="TM-X003")
            argv += ["--mount", f"type=bind,source={host},target={target}" + (",readonly" if readonly else "")]
        for k, v in env.items():
            argv += ["-e", f"{k}={v}"]
        return [*argv, "--entrypoint", entrypoint, self.image]

    async def _sh(self, script: str) -> Proc:
        if self.image:
            docker = ["docker", "run", "--rm", "--entrypoint", "sh", self.image, "-c", script]
            proc = await spawn(docker, cwd=None, env=self._host_env(), timeout=120)
        else:
            proc = await spawn(["sh", "-c", script], cwd=None, env=self._host_env(), timeout=120)
        if proc.returncode != 0:
            raise ToolchainError(
                f"probe failed: {_tail(proc.stderr)}", code="TM-T005", hint="run `texmodel run doctor`"
            )
        return proc


__all__ = ["Compiler", "ImageInfo", "Versions"]
