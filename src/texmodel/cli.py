"""The `texmodel` command line. Only this module formats output (E5)."""

import dataclasses
import importlib.metadata
import json
import shutil

import typer

app = typer.Typer(pretty_exceptions_enable=False, help="Typed models for LaTeX.", no_args_is_help=True)

# tool -> what is lost without it
TOOLS = {
    "lualatex": "no compiling (make --to pdf)",
    "latexmk": "no compiling: the single rerun strategy (C8)",
    "kpsewhich": "no package probing",
    "gs": "no PDF/A or PDF/X checks (Ghostscript)",
    "verapdf": "no PDF/A checks",
}
REQUIRED = ("lualatex", "latexmk")


@dataclasses.dataclass(frozen=True)
class ToolStatus:
    name: str
    path: str | None
    gap: str


def probe_tools() -> list[ToolStatus]:
    return [ToolStatus(name, shutil.which(name), gap) for name, gap in TOOLS.items()]


@app.callback()
def main() -> None:
    """Typed models for LaTeX."""


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(importlib.metadata.version("texmodel"))


@app.command()
def doctor(as_json: bool = typer.Option(False, "--json", help="Machine-readable output.")) -> None:
    """Report what this machine can do. Exit 3 when a required tool is missing."""
    tools = probe_tools()
    if as_json:
        typer.echo(json.dumps([dataclasses.asdict(t) for t in tools], indent=2))
    else:
        for t in tools:
            typer.echo(f"{'ok     ' if t.path else 'missing'} {t.name:10} {t.path or t.gap}")
    if any(t.path is None and t.name in REQUIRED for t in tools):
        raise typer.Exit(3)
