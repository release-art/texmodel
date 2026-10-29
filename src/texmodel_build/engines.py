"""Engine profiles (M13): what differs between engines. v1 has one, LuaLaTeX."""

import dataclasses
from collections.abc import Callable, Sequence

from texmodel.errors import DeclarationError

from ._internal.logparse import parse_log
from .diagnostics import Diagnostic, Measure


@dataclasses.dataclass(frozen=True)
class Engine:
    name: str
    binary: str
    # latexmk options choosing this engine; shell escape is off, and a package must declare it to get it (C3).
    latexmk_args: tuple[str, ...]
    parse_log: Callable[[str, Sequence[Measure]], tuple[Diagnostic, ...]]


# Before the document (latexmk's `%P`): mark each TeX file opened and closed in the log, `texmodel:open:<name>` and
# `texmodel:close` on lines of their own, so a warning that names only its line is placed in its file. TeX's own
# `(name` ... `)` cannot be followed: message and box text carry unbalanced parentheses. The callback replaces LuaTeX's
# printing of every file, so it prints what LuaTeX does (`(file)`, `{map}`, `<image>`, `<font>`, `<<font>>`): the font
# listing `fonts.embedded` reads stays, and the PDF is unchanged. TeX reads the text before Lua does and latexmk quotes
# it with `"`, so its braces balance and it has no `"`, `%`, `#` or `~`.
_FILE_MARKS = r"""
    \directlua{
      local open = {'(', '{', '<', '<', '<<'}
      local close = {')', '}', '>', '>', '>>'}
      luatexbase.add_to_callback('start_file', function(category, name)
        if category == 1 then texio.write_nl('log', 'texmodel:open:<' .. name .. '>') texio.write_nl('') end
        texio.write(open[category] .. name)
      end, 'texmodel')
      luatexbase.add_to_callback('stop_file', function(category)
        texio.write(close[category])
        if category == 1 then texio.write_nl('log', 'texmodel:close') texio.write_nl('') end
      end, 'texmodel')
    }
"""

LUALATEX = Engine(
    name="lualatex",
    binary="lualatex",
    latexmk_args=(
        "-pdf",
        "-pdflatex=lualatex --no-shell-escape %O %P",
        "-pretex=" + " ".join(_FILE_MARKS.split()),  # one line: it is a command-line argument
    ),
    parse_log=parse_log,
)

ENGINES = {e.name: e for e in (LUALATEX,)}


def get_engine(name: str) -> Engine:
    try:
        return ENGINES[name]
    except KeyError:
        raise DeclarationError(f"unknown engine {name!r}", code="TM-D010", hint=f"known: {sorted(ENGINES)}") from None


__all__ = ["ENGINES", "Engine", "LUALATEX", "get_engine"]
