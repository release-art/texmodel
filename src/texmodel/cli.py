"""The `texmodel` command line. Only this module formats output (E5)."""

import functools
import importlib.metadata
import logging
import pathlib
from collections.abc import Callable
from typing import Annotated, Any

import typer

from ._internal.loader import load_document, load_package
from .config import Config, load_config
from .drift import check_drift
from .errors import DeclarationError, TexmodelError, ValidationError
from .package import Package, generator_version

app = typer.Typer(pretty_exceptions_enable=False, help="Typed models for LaTeX.", no_args_is_help=True)


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


def _exits(fn: Callable[..., None]) -> Callable[..., None]:
    """Errors print once, to stderr, with their code and hint; exit 2."""

    def report(exc: TexmodelError) -> None:
        where = f" at {exc.path}" if exc.path and isinstance(exc, ValidationError) else ""
        typer.echo(f"error {exc.code}{where}: {exc}" + (f"\n  hint: {exc.hint}" if exc.hint else ""), err=True)

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            fn(*args, **kwargs)
        except TexmodelError as exc:
            report(exc)
            raise typer.Exit(2) from exc
        except ExceptionGroup as group:  # an invalid document: every violation, not the first (E2)
            problems = [e for e in group.exceptions if isinstance(e, TexmodelError)]
            if len(problems) != len(group.exceptions):
                raise
            for exc in problems:
                report(exc)
            raise typer.Exit(2) from group

    return wrapper


def _project() -> tuple[pathlib.Path, Config, Package]:
    root = pathlib.Path.cwd()
    config = load_config(root / "pyproject.toml")
    if not config.package:
        raise DeclarationError(
            "no package declared", code="TM-D023", hint='set [tool.texmodel] package = "module:attr"'
        )
    return root, config, load_package(config.package, root)


@app.command()
@_exits
def build() -> None:
    """Write the package's generated files (the `.sty`) into the output directory."""
    root, config, package = _project()
    for rel, text in package.files().items():
        path = root / config.output / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {path.relative_to(root)}")


@app.command()
@_exits
def render(
    document: Annotated[str, typer.Argument(help="module:attribute: a str from Package.document(), or a function.")],
    output: Annotated[pathlib.Path | None, typer.Option("--output", "-o", help="Default <attribute>.tex.")] = None,
) -> None:
    """Write a document to a .tex file. An invalid document reports every violation and exits 2."""
    target = output or pathlib.Path(f"{document.partition(':')[2]}.tex")
    text = load_document(document, pathlib.Path.cwd())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    typer.echo(f"wrote {target}")


@app.command()
@_exits
def check() -> None:
    """Fail if a committed generated file is stale, missing or orphaned. Exit 0 ok, 1 drift."""
    root, config, package = _project()
    out = root / config.output
    drift = check_drift(package.files(), out, owned=("*.sty",), version=generator_version())
    for label, names in (("stale", drift.stale), ("missing", drift.missing), ("orphaned", drift.orphaned)):
        for name in names:
            typer.echo(f"{label:8} {config.output}/{name}")
    for note in drift.notes:
        typer.echo(f"note     {note}")
    if drift.stale or drift.missing or drift.orphaned:
        typer.echo("run `texmodel build` and commit the result", err=True)
        raise typer.Exit(1)
    typer.echo("ok: generated files are current")
