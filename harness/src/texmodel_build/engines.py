"""Engine profiles (M13): what differs between engines. v1 has one, LuaLaTeX."""

import dataclasses
from collections.abc import Callable

from texmodel.errors import DeclarationError

from ._internal.logparse import parse_log
from .diagnostics import Diagnostic


@dataclasses.dataclass(frozen=True)
class Engine:
    name: str
    binary: str
    # latexmk options choosing this engine; shell escape is off, and a package must declare it to get it (C3).
    latexmk_args: tuple[str, ...]
    parse_log: Callable[[str], tuple[Diagnostic, ...]]


LUALATEX = Engine(
    name="lualatex",
    binary="lualatex",
    latexmk_args=("-pdf", "-pdflatex=lualatex --no-shell-escape %O %S"),
    parse_log=parse_log,
)

ENGINES = {e.name: e for e in (LUALATEX,)}


def get_engine(name: str) -> Engine:
    try:
        return ENGINES[name]
    except KeyError:
        raise DeclarationError(f"unknown engine {name!r}", code="TM-D010", hint=f"known: {sorted(ENGINES)}") from None
