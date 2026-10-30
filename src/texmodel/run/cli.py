"""The `texmodel run` commands: compile, build targets, clean, verify, doctor. Only this module prints."""

import asyncio
import dataclasses
import functools
import json
import logging
import pathlib
import shutil
from collections.abc import Callable
from typing import Annotated, Any

import typer

from texmodel.errors import DeclarationError, TexmodelError
from texmodel.pointer import load_plan

from ._internal.styscan import needed
from .compiler import Compiler
from .config import BuildConfig, load_build_config
from .engines import get_engine
from .errors import ToolchainError
from .result import CompileResult
from .targets import build_targets
from .verify import FileReport, Profile, expand_targets, registered, verify_files

logger = logging.getLogger(__name__)

app = typer.Typer(
    pretty_exceptions_enable=False, help="Compile and verify LaTeX built from texmodel.", no_args_is_help=True
)

# tool -> what is lost without it
TOOLS = {
    "lualatex": "no compiling (make --to pdf)",
    "latexmk": "no compiling: the single rerun strategy (C8)",
    "kpsewhich": "no package probing",
    "gs": "no PDF/A or PDF/X checks (Ghostscript)",
    "verapdf": "no PDF/A checks",
    "docker": "no reference container (C8)",
}
REQUIRED = ("lualatex", "latexmk")
BUILD_DIR = pathlib.Path(".texmodel")


@dataclasses.dataclass(frozen=True)
class ToolStatus:
    name: str
    path: str | None
    gap: str


def probe_tools() -> list[ToolStatus]:
    return [ToolStatus(name, shutil.which(name), gap) for name, gap in TOOLS.items()]


def _exits(fn: Callable[..., None]) -> Callable[..., None]:
    """Errors print once, to stderr: exit 3 for a missing tool or image, 2 for bad usage or declarations."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            fn(*args, **kwargs)
        except TexmodelError as exc:
            typer.echo(f"error {exc.code}: {exc}" + (f"\n  hint: {exc.hint}" if exc.hint else ""), err=True)
            raise typer.Exit(3 if isinstance(exc, ToolchainError) else 2) from exc

    return wrapper


def _config() -> BuildConfig | None:
    path = pathlib.Path("pyproject.toml")
    if not path.is_file():
        return None
    try:
        return load_build_config(path)
    except DeclarationError as exc:
        if exc.code == "TM-D001":  # a pyproject without a [tool.texmodel.run] table is simply not configured
            return None
        raise


def _compiler(image: str | None, local: bool, roots: list[pathlib.Path], epoch: int | None, passes: int) -> Compiler:
    config = _config()
    chosen = None if local else (image or (config.image if config else "")) or None
    return Compiler(
        engine=get_engine(config.engine if config else "lualatex"),
        image=chosen,
        roots=tuple(roots),
        font_cache=BUILD_DIR / "fonts",
        max_passes=passes,
        epoch=epoch,
        measures=tuple(config.measures.values()) if config else (),
    )


def _show(result: CompileResult) -> None:
    for d in result.diagnostics:
        where = (f" {d.file or '?'}:{d.line}" if d.line else "") + (f" [{d.path}]" if d.path else "")
        typer.echo(f"{d.severity.value:7} {d.code}{where} {d.message}" + (f" (x{d.count})" if d.count > 1 else ""))
    state = "ok" if result.ok else "FAILED"
    typer.echo(f"{state} {result.pdf or '(no pdf)'} ({result.pages} pages, {result.passes} passes, {result.seconds}s)")


Image = Annotated[str | None, typer.Option(help="Reference image tag (default: [tool.texmodel.run] image).")]
Local = Annotated[bool, typer.Option("--local", help="Run on this machine instead of in the image.")]
Roots = Annotated[list[pathlib.Path], typer.Option("--root", help="Asset root, earlier wins. Repeatable.")]
Epoch = Annotated[int | None, typer.Option(help="Reproducible mode: pin SOURCE_DATE_EPOCH to this value.")]
Passes = Annotated[int, typer.Option(help="Maximum latexmk runs.")]
AsJson = Annotated[bool, typer.Option("--json", help="Machine-readable output.")]


async def _image_status(tag: str) -> dict[str, Any]:
    """What the configured image can do, or why it cannot be used."""
    try:
        comp = Compiler(image=tag)
        v = await comp.check_ready()
        info = await comp.image_info()
        return {
            "image": tag,
            "ok": True,
            "digest": info.digest if info else "",
            "revision": info.revision if info else "",
            "engine": v.engine_version,
            "latexmk": v.latexmk_version,
            "missing": [{"name": n, "gap": TOOLS[n]} for n in ("kpsewhich", "gs", "verapdf") if n not in v.tools],
        }
    except ToolchainError as exc:
        return {"image": tag, "ok": False, "error": str(exc), "hint": exc.hint}


async def _sty_report(globs: list[str], image: str) -> dict[str, Any]:
    """What the files matching `globs` load (D2) and which of it the toolchain, here or in `image`, cannot find."""
    paths = sorted({p for g in globs for p in pathlib.Path().glob(g) if p.is_file()})
    if not paths:
        raise DeclarationError("no file matches --sty", code="TM-D014", hint="pass a glob such as 'res/*.sty'")
    own = {p.stem for p in paths}  # a package may load its siblings
    files, unchecked = needed(p.read_text(encoding="utf-8", errors="replace") for p in paths)
    files = [f for f in files if f.partition(".")[0] not in own]
    missing = await Compiler(image=image or None).missing_files(files)
    return {"scanned": [str(p) for p in paths], "checked": len(files), "missing": list(missing), "unchecked": unchecked}


def _show_sty(report: dict[str, Any]) -> None:
    for name in report["missing"]:
        typer.echo(f"missing {name}")
    for name in report["unchecked"]:
        typer.echo(f"unchecked {name}: not a plain file name, so not looked up")
    if report["missing"]:
        packages = [f.removesuffix(".sty") for f in report["missing"] if f.endswith(".sty")]
        typer.echo("install: tlmgr install " + " ".join(packages) if packages else "install: see tlmgr search --file")
        typer.echo("(a TeX Live package can have another name than its file: tlmgr search --global --file <file>)")
    else:
        typer.echo(f"ok: the {report['checked']} file(s) loaded by {len(report['scanned'])} scanned file(s) are found")


@app.command()
@_exits
def doctor(
    as_json: AsJson = False,
    sty: Annotated[
        list[str] | None,
        typer.Option(
            help="Glob of .sty/.cls files: report which files they load that the toolchain lacks. Repeatable."
        ),
    ] = None,
) -> None:
    """Report what this machine can do, and what the configured image can; with --sty, which files a package loads
    are missing. Exit 3 when nothing can compile or a file is missing."""
    tools = probe_tools()
    for t in tools:
        logger.debug("probe %s -> %s", t.name, t.path)
    config = _config()
    image = asyncio.run(_image_status(config.image)) if config and config.image else None
    ready = image["ok"] if image else all(t.path for t in tools if t.name in REQUIRED)
    report = asyncio.run(_sty_report(sty, config.image if config else "")) if sty and ready else None
    if as_json:
        shown = {"tools": [dataclasses.asdict(t) for t in tools], "image": image, "sty": report}
        typer.echo(json.dumps(shown, indent=2))
    else:
        for t in tools:
            typer.echo(f"{'ok     ' if t.path else 'missing'} {t.name:10} {t.path or t.gap}")
        if image and image["ok"]:
            typer.echo(f"image   {image['image']}: {image['engine']}, latexmk {image['latexmk']}")
            for m in image["missing"]:
                typer.echo(f"missing {m['name']:10} in image: {m['gap']}")
        elif image:
            typer.echo(f"image   {image['image']}: {image['error']} ({image['hint']})")
        if report:
            _show_sty(report)
    if not ready or (report and report["missing"]):
        raise typer.Exit(3)


@app.command("compile")
@_exits
def compile_(
    source: pathlib.Path,
    outdir: Annotated[
        pathlib.Path | None, typer.Option("--outdir", "-o", help="Default: .texmodel/build/<name>.")
    ] = None,
    image: Image = None,
    local: Local = False,
    root: Roots = [],  # noqa: B006 - typer reads the default, it is never mutated
    epoch: Epoch = None,
    passes: Passes = 5,
    as_json: AsJson = False,
    plan: Annotated[
        str | None, typer.Option(help="Pointer to the Plan that wrote SOURCE: diagnostics then name the component.")
    ] = None,
) -> None:
    """Compile SOURCE with latexmk. Exit 0 ok, 1 errors in the document, 3 tool or image missing."""
    comp = _compiler(image, local, root, epoch, passes)
    found = load_plan(plan, pathlib.Path.cwd()) if plan else None
    result = asyncio.run(comp.compile(source, outdir or BUILD_DIR / "build" / source.stem, plan=found))
    if as_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
    else:
        _show(result)
    if not result.ok:
        raise typer.Exit(1)


@app.command()
@_exits
def build(
    names: Annotated[list[str] | None, typer.Argument(help="Targets to build (default: all).")] = None,
    jobs: Annotated[int, typer.Option("--jobs", "-j")] = 1,
    image: Image = None,
    local: Local = False,
    root: Roots = [],  # noqa: B006
    epoch: Epoch = None,
    passes: Passes = 5,
) -> None:
    """Build the targets declared in [tool.texmodel.run.targets]."""
    config = _config()
    if config is None or not config.targets:
        raise DeclarationError("no targets declared", code="TM-D011", hint="add [tool.texmodel.run.targets.<name>]")
    unknown = [n for n in names or [] if n not in config.targets]
    if unknown:
        raise DeclarationError(f"unknown targets {unknown}", code="TM-D012", hint=f"declared: {sorted(config.targets)}")
    chosen = [config.targets[n] for n in names or config.targets]
    compiler = _compiler(image, local, root, epoch, passes)
    summary = asyncio.run(
        build_targets(chosen, compiler, root=pathlib.Path.cwd(), outdir=BUILD_DIR / "build", jobs=jobs)
    )
    for line in summary.lines():
        typer.echo(line)
    if not summary.ok:
        raise typer.Exit(1)


def _show_report(report: FileReport) -> None:
    if report.exempt is not None:
        typer.echo(f"exempt  {report.path}: {report.exempt}")
        return
    typer.echo(f"{'ok     ' if report.ok else 'FAILED'} {report.path}")
    for f in report.findings:
        page = f" (page {f.page})" if f.page is not None else ""
        typer.echo(f"  {f.severity.value:7} [{f.check}]{page} {f.message}")


@app.command()
@_exits
def verify(
    paths: Annotated[list[pathlib.Path], typer.Argument(help="Files, or directories (every PDF beneath).")],
    check: Annotated[
        list[str] | None, typer.Option(help="Verifier to run. Repeatable. Default: the profile's, else all.")
    ] = None,
    profile: Annotated[str | None, typer.Option(help="A [tool.texmodel.run.profiles.<name>] table.")] = None,
    exempt: Annotated[
        list[str] | None, typer.Option(help="GLOB=reason: out of scope, listed with the reason, never fails.")
    ] = None,
    exclude: Annotated[
        list[str] | None, typer.Option(help="Glob (relative to a directory argument) to drop silently.")
    ] = None,
    jobs: Annotated[int, typer.Option("--jobs", "-j")] = 1,
    as_json: AsJson = False,
) -> None:
    """Run verifier plugins over built files. Anything that cannot be confirmed fails (exit 1)."""
    config = _config()
    if profile:
        if config is None or profile not in config.profiles:
            raise DeclarationError(
                f"unknown profile {profile!r}", code="TM-D013", hint="add [tool.texmodel.run.profiles.<name>]"
            )
        chosen = config.profiles[profile]
    else:
        chosen = Profile()
    if check:
        chosen = dataclasses.replace(chosen, checks=tuple(check))
    exemptions = {**(config.exempt if config else {}), **dict(e.split("=", 1) for e in exempt or [])}
    found = expand_targets(paths, exclude or [])
    reports = asyncio.run(verify_files(found, chosen, registered(), exemptions, jobs=jobs))
    if as_json:
        typer.echo(
            json.dumps(
                [
                    {
                        "path": str(r.path),
                        "ok": r.ok,
                        "exempt": r.exempt,
                        "findings": [{**dataclasses.asdict(f), "severity": f.severity.value} for f in r.findings],
                    }
                    for r in reports
                ],
                indent=2,
            )
        )
    else:
        for report in reports:
            _show_report(report)
    if not all(r.ok for r in reports):
        raise typer.Exit(1)


@app.command()
@_exits
def clean(
    source: pathlib.Path,
    outdir: Annotated[pathlib.Path | None, typer.Option("--outdir", "-o")] = None,
    everything: Annotated[bool, typer.Option("--all", help="Also remove the PDF (latexmk -C).")] = False,
    image: Image = None,
    local: Local = False,
) -> None:
    """Remove build output for SOURCE."""
    compiler = _compiler(image, local, [], None, 5)
    asyncio.run(compiler.clean(source, outdir or BUILD_DIR / "build" / source.stem, everything=everything))
