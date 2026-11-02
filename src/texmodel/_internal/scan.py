"""Reading the declaration forms of a hand-written package (M9): `\\newcommand`, `\\providecommand`,
`\\DeclareRobustCommand`, `\\def`, `\\newenvironment`, xparse's `\\NewDocumentCommand` family, and the names with no
arguments that `\\newlength`, `\\newsavebox`, `\\newfontfamily`, etoolbox's `\\newtoggle` and `\\newif` (with
`\\Xtrue` and `\\Xfalse`) declare, and expl3's `\\cs_new` functions (`expl3=True` reads a library block, which texmodel
wraps in `\\ExplSyntaxOn`). Colours (`\\definecolor`, `\\colorlet`) and counters (`\\newcounter`) are
names of their own.

Only these forms are read, so a name defined any other way is reported as missing rather than guessed at. An xparse
argument type that texmodel does not model is reported as `?`, which matches no declaration. The reading is
`_internal.tex`'s: tokens, so a comment, a verbatim and an `\\iffalse` declare nothing.
"""

from .tex import Declaration, Form, declarations, xparse_letters

__all__ = ["scan_colours", "scan_counters", "scan_declarations", "xparse_letters"]

_NAMES = frozenset({Form.COMMAND, Form.ENVIRONMENT, Form.XPARSE, Form.REGISTER, Form.FUNCTION})


def _names(found: list[Declaration], form: Form) -> frozenset[str]:
    return frozenset(d.name for d in found if d.form is form)


def scan_colours(text: str, *, expl3: bool = False) -> frozenset[str]:
    """The colour names `\\definecolor`, `\\colorlet` and `\\providecolor` define: not control sequences."""
    return _names(declarations(text, expl3=expl3), Form.COLOUR)


def scan_counters(text: str, *, expl3: bool = False) -> frozenset[str]:
    """The counters `\\newcounter` defines: not control sequences either."""
    return _names(declarations(text, expl3=expl3), Form.COUNTER)


def scan_declarations(text: str, prefix: str = "", *, expl3: bool = False) -> dict[str, str]:
    """`{"cdTalkAboutMe": "[2][]"}`: each name starting with `prefix` that `text` defines, with its signature in the
    form `render.signature` writes (`""` for none, `[n]`, or `[n][]` when the first argument is optional; for an xparse
    definition its argument types as letters). The first definition of a name wins."""
    out: dict[str, str] = {}
    for d in declarations(text, expl3=expl3):
        if d.form in _NAMES and d.name.startswith(prefix):
            out.setdefault(d.name, d.signature)
    return out
