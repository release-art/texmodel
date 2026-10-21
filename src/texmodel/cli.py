"""The `texmodel` command line. Only this module formats output (E5)."""

import dataclasses
import functools
import importlib.metadata
import json
import logging
import pathlib
import shutil
from collections.abc import Callable
from typing import Annotated, Any

import typer

from .compiler import Compiler, Limits
from .config import Config, load_config
from .engines import get_engine
from .errors import DeclarationError, TexmodelError, ToolchainError
from .result import CompileResult
from .targets import build_targets

logger = logging.getLogger(__name__)

app = typer.Typer(pretty_exceptions_enable=False, help="Typed models for LaTeX.", no_args_is_help=True)

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


def _config() -> Config | None:
    path = pathlib.Path("pyproject.toml")
    if not path.is_file():
        return None
    try:
        return load_config(path)
    except DeclarationError as exc:
        if exc.code == "TM-D001":  # a pyproject without a [tool.texmodel] table is simply not configured
            return None
        raise


def _compiler(image: str | None, local: bool, roots: list[pathlib.Path], epoch: int | None, passes: int) -> Compiler:
    config = _config()
    chosen = None if local else (image or (config.image if config else "")) or None
    return Compiler(
        engine=get_engine(config.engine if config else "lualatex"),
        image=chosen,
        roots=tuple(roots),
        cache_dir=BUILD_DIR / "cache",
        font_cache=BUILD_DIR / "fonts",
        max_passes=passes,
        epoch=epoch,
        limits=Limits(),
    )


def _show(result: CompileResult) -> None:
    for d in result.diagnostics:
        where = f" {d.file or '?'}:{d.line}" if d.line else ""
        typer.echo(f"{d.severity.value:7} {d.code}{where} {d.message}" + (f" (x{d.count})" if d.count > 1 else ""))
    state = "ok" if result.ok else "FAILED"
    typer.echo(
        f"{state} {result.pdf or '(no pdf)'} ({result.pages} pages, {result.passes} passes, {result.seconds}s)"
        + (" [cache hit]" if result.cache_hit else "")
    )


Image = Annotated[str | None, typer.Option(help="Reference image tag (default: [tool.texmodel] image).")]
Local = Annotated[bool, typer.Option("--local", help="Run on this machine instead of in the image.")]
Roots = Annotated[list[pathlib.Path], typer.Option("--root", help="Asset root, earlier wins. Repeatable.")]
Epoch = Annotated[int | None, typer.Option(help="Reproducible mode: pin SOURCE_DATE_EPOCH to this value.")]
Passes = Annotated[int, typer.Option(help="Maximum latexmk runs.")]
AsJson = Annotated[bool, typer.Option("--json", help="Machine-readable output.")]


@app.callback()
def main(verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="-v info, -vv debug (to stderr).")) -> None:
    """Typed models for LaTeX."""
    if verbose:
        handler = logging.StreamHandler()  # stderr; stdout carries results only
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        log = logging.getLogger("texmodel")
        log.addHandler(handler)
        log.setLevel(logging.DEBUG if verbose > 1 else logging.INFO)


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(importlib.metadata.version("texmodel"))


@app.command()
@_exits
def doctor(as_json: AsJson = False) -> None:
    """Report what this machine can do, and what the configured image can. Exit 3 when nothing can compile."""
    tools = probe_tools()
    for t in tools:
        logger.debug("probe %s -> %s", t.name, t.path)
    config = _config()
    image: dict[str, Any] | None = None
    ready = all(t.path for t in tools if t.name in REQUIRED)
    if config and config.image:
        try:
            comp = Compiler(image=config.image)
            v = comp.check_ready()
            info = comp.image_info
            image = {
                "image": config.image,
                "ok": True,
                "digest": info.digest if info else "",
                "revision": info.revision if info else "",
                "engine": v.engine_version,
                "latexmk": v.latexmk_version,
                "missing": [{"name": n, "gap": TOOLS[n]} for n in ("kpsewhich", "gs", "verapdf") if n not in v.tools],
            }
            ready = True
        except ToolchainError as exc:
            image = {"image": config.image, "ok": False, "error": str(exc), "hint": exc.hint}
            ready = False
    if as_json:
        typer.echo(json.dumps({"tools": [dataclasses.asdict(t) for t in tools], "image": image}, indent=2))
    else:
        for t in tools:
            typer.echo(f"{'ok     ' if t.path else 'missing'} {t.name:10} {t.path or t.gap}")
        if image and image["ok"]:
            typer.echo(f"image   {image['image']}: {image['engine']}, latexmk {image['latexmk']}")
            for m in image["missing"]:
                typer.echo(f"missing {m['name']:10} in image: {m['gap']}")
        elif image:
            typer.echo(f"image   {image['image']}: {image['error']} ({image['hint']})")
    if not ready:
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
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Ignore and do not fill the compile cache.")] = False,
    as_json: AsJson = False,
) -> None:
    """Compile SOURCE with latexmk. Exit 0 ok, 1 errors in the document, 3 tool or image missing."""
    comp = _compiler(image, local, root, epoch, passes)
    if no_cache:
        comp = dataclasses.replace(comp, cache_dir=None)
    result = comp.compile(source, outdir or BUILD_DIR / "build" / source.stem)
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
    """Build the targets declared in [tool.texmodel.targets]."""
    config = _config()
    if config is None or not config.targets:
        raise DeclarationError("no targets declared", code="TM-D011", hint="add [tool.texmodel.targets.<name>]")
    unknown = [n for n in names or [] if n not in config.targets]
    if unknown:
        raise DeclarationError(f"unknown targets {unknown}", code="TM-D012", hint=f"declared: {sorted(config.targets)}")
    chosen = [config.targets[n] for n in names or config.targets]
    summary = build_targets(
        chosen,
        _compiler(image, local, root, epoch, passes),
        root=pathlib.Path.cwd(),
        outdir=BUILD_DIR / "build",
        jobs=jobs,
    )
    for line in summary.lines():
        typer.echo(line)
    if not summary.ok:
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
    _compiler(image, local, [], None, 5).clean(
        source, outdir or BUILD_DIR / "build" / source.stem, everything=everything
    )
