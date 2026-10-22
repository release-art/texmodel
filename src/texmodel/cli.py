"""The `texmodel` command line. Only this module formats output (E5)."""

import functools
import importlib.metadata
import json
import logging
import pathlib
from collections.abc import Callable
from typing import Annotated, Any

import typer

from .config import Config, load_config
from .drift import check_drift
from .errors import DeclarationError, TexmodelError, ValidationError
from .package import Package, generator_version
from .plan import Plan
from .pointer import load_document, load_package
from .spec import json_schema

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
            "no package declared",
            code="TM-D023",
            hint='set [tool.texmodel] package = "module:object" or "module:getter()"',
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


def _write(rendered: str | Plan, target: pathlib.Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered.text if isinstance(rendered, Plan) else rendered, encoding="utf-8")
    typer.echo(f"wrote {target}")


@app.command()
@_exits
def schema() -> None:
    """Write the JSON Schema of the package's data (every component and value) to `schema_output`."""
    root, config, package = _project()
    if not config.schema_output:
        raise DeclarationError(
            "no schema_output declared", code="TM-D033", hint='set [tool.texmodel] schema_output = "schema.json"'
        )
    path = root / config.schema_output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_schema(package), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    typer.echo(f"wrote {path.relative_to(root)}")


@app.command()
@_exits
def render(
    document: Annotated[
        str | None,
        typer.Argument(
            help="Pointer (module:object, module:getter()) to a str or Plan from Package.document() / plan(). "
            "Without one, every [tool.texmodel.documents] entry is written to its path."
        ),
    ] = None,
    output: Annotated[pathlib.Path | None, typer.Option("--output", "-o", help="Default <attribute>.tex.")] = None,
) -> None:
    """Write a document to a .tex file, or all configured documents. An invalid document reports every violation and
    exits 2."""
    root = pathlib.Path.cwd()
    if document is not None:
        target = output or pathlib.Path(f"{document.partition(':')[2].removesuffix('()').rpartition('.')[2]}.tex")
        _write(load_document(document, root), target)
        return
    documents = load_config(root / "pyproject.toml").documents
    if output or not documents:
        raise DeclarationError(
            "no document to render" if not documents else "--output needs a document pointer",
            code="TM-D031",
            hint='pass a pointer, or declare [tool.texmodel.documents] "deck.tex" = "module:plan()"',
        )
    for name, pointer in sorted(documents.items()):
        _write(load_document(pointer, root), root / name)


def _check_interface(root: pathlib.Path, config: Config, package: Package) -> bool:
    """An adopted package (M9): every declared component is defined in `sources` with its declared signature."""
    paths = sorted(p for glob in config.sources for p in root.glob(glob) if p.is_file())
    if not paths:
        raise DeclarationError(
            f"{package.name} is adopted but `sources` matches no file",
            code="TM-D030",
            hint='set [tool.texmodel] sources = ["res/brand/*.sty"]',
        )
    violations = package.check_interface(*(p.read_text(encoding="utf-8", errors="replace") for p in paths))
    for v in violations:
        typer.echo(f"{v.code} {v.path}: {v.message}")
    if not violations:
        typer.echo(f"ok: {len(paths)} source file(s) define what {package.name} declares")
    return bool(violations)


def _check_generated(root: pathlib.Path, config: Config, package: Package) -> bool:
    out = root / config.output
    drift = check_drift(package.files(), out, owned=("*.sty",), version=generator_version())
    for label, names in (("stale", drift.stale), ("missing", drift.missing), ("orphaned", drift.orphaned)):
        for name in names:
            typer.echo(f"{label:8} {config.output}/{name}")
    plan = package.render_plan()
    for name in drift.stale:  # a stale file is named by component, as a document is
        for e in plan.edits((out / name).read_text(encoding="utf-8", errors="replace")):
            typer.echo(f"{e.kind.value:8} {config.output}/{name} {e.path}: {e.found or e.expected}")
    for note in drift.notes:
        typer.echo(f"note     {note}")
    if drift.stale or drift.missing or drift.orphaned:
        typer.echo("run `texmodel build` and commit the result", err=True)
        return True
    typer.echo("ok: generated files are current")
    return False


def _check_documents(root: pathlib.Path, config: Config) -> bool:
    """Each committed document against what the model renders now, by path (like `terraform plan`): a changed, removed
    or added line names the component that writes it, so a hand edit and a stale render read the same."""
    failed = False
    for name, pointer in sorted(config.documents.items()):
        rendered = load_document(pointer, root)
        committed = root / name
        if not committed.is_file():
            typer.echo(f"missing  {name}")
            failed = True
        elif isinstance(rendered, Plan):
            for e in rendered.edits(committed.read_text(encoding="utf-8")):
                typer.echo(f"{e.kind.value:8} {name} {e.path}: {e.found or e.expected}")
                failed = True
        elif committed.read_text(encoding="utf-8") != rendered:
            typer.echo(f"stale    {name}")
            failed = True
    if config.documents and not failed:
        typer.echo(f"ok: {len(config.documents)} document(s) match the model")
    if failed:
        typer.echo("run `texmodel render` and commit the result", err=True)
    return failed


@app.command()
@_exits
def check() -> None:
    """Fail if a generated file is stale, missing or orphaned, an adopted package's interface drifted, or a document
    differs from what the model renders. Exit 0 ok, 1 drift."""
    root, config, package = _project()
    failed = _check_interface(root, config, package) if package.adopted else _check_generated(root, config, package)
    if _check_documents(root, config) or failed:
        raise typer.Exit(1)
