"""The calls read from a document's tokens are the calls TeX makes: one compile with the stubs, compared."""

import random
import re
from collections.abc import Mapping, Sequence

import pytest
from test_texmodel.test_calls import CLASSES, pkg
from test_texmodel.test_hand_edits import entries, rows_pkg

from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401
from texmodel._internal.calls import ParsedCall, Unreadable, parse_calls
from texmodel.document import Document
from texmodel.hand_edits import _classes  # pyright: ignore[reportPrivateUsage]
from texmodel.preamble import PreambleSlots
from texmodel.run.compiler import Compiler
from texmodel.run.errors import CompileError
from texmodel.run.testkit import run_probes
from texmodel.testing import Call, Component, stub_tex
from texmodel.types import Raw

pytestmark = [pytest.mark.tex, pytest.mark.timeout(300)]


async def calls_by_tex(comp: Compiler, tex: str, stubs: Sequence[Component], files: Mapping[str, str]) -> list[Call]:
    """The calls the stubs log when `tex` compiles, in document order: the oracle the parser is held to."""
    stubbed = tex.replace(r"\begin{document}", stub_tex(stubs) + "\n" + r"\begin{document}", 1)
    found = await run_probes(comp, stubbed, files)
    numbered = sorted((int(m.name.removeprefix("call")), m.value) for m in found if re.fullmatch(r"call\d+", m.name))
    return [Call.parse(value) for _, value in numbered]


HAND = r"""
\wrPara{a}
\wrPara x
\wrPara{ a }
\wrPara{a  b}
\wrPara{a
 b}
\wrPara{a % c
 b}
\wrPara{a%
 b}
\wrPara{R\& D 50\%}
\wrPara{{x}}
\wrPara{ {x} }
\wrPara
{a}
\wrPara{a}{b}
\wrNote{n}
\wrNote [L] {n}
\wrNote[L
]{n}
\wrNote[{a]b}]{n}
\wrNote[]{n}
\wrNote[{x}]{n}
\wrAngle{n} <m>
\wrAngle{n}
\wrAngle{n}<{a>b}>
\wrStars[3cm]*(x)
\wrStars (y)
\wrStars[]*( z )
% \wrPara{commented}
\wrPara{a} % \wrPara{trailing}
\iffalse
\wrPara{dead}
\fi
\iffalse
\wrPara{dead}
\else
\wrPara{alive}
\fi
\begin{wrBox}{T}
\wrPara{in}
\end{wrBox}
\begin {wrBox} {  T T }\wrPara x
\end {wrBox}
\wrPara{a\par b}
\wrPara{#1 ##2}
\wrPara{a

b}
\wrPara{a%

b}
\wrPara{a


b}
\wrPara{\verb|x|}
\wrPara{a~b}
\wrPara{\#}
\wrPara{$x$}
\wrPara\relax
\wrPara\&
\wrPara{é\relax ö ß}
\wrPara{\relaxé}
"""

ATOMS = ["a", "b c", " ", "\n", "\n\n", r"\&", r"\%", r"\textbf{x}", "{x}", "{ y }", "%c\n", "~", r"\par ", "é", "$z$"]
GAPS = ["", " ", "\n", "  \n  ", "%c\n", " %c\n "]


def generated(seed: int, lines: int) -> str:
    rnd = random.Random(seed)

    def content(depth: int = 0) -> str:
        parts = [
            rnd.choice(ATOMS) if depth > 1 or rnd.random() < 0.7 else "{" + content(depth + 1) + "}"
            for _ in range(rnd.randint(0, 4))
        ]
        return "".join(parts)

    def required() -> str:
        return rnd.choice(GAPS) + (" x" if rnd.random() < 0.15 else "{" + content() + "}")

    def optional() -> str:
        return "" if rnd.random() < 0.5 else rnd.choice(GAPS) + "[" + content().replace("]", "") + "]"

    out = []
    for _ in range(lines):
        pick = rnd.choice(["Para", "Note", "Box"])
        line = {
            "Para": lambda: r"\wrPara" + required(),
            "Note": lambda: r"\wrNote" + optional() + required(),
            "Box": lambda: r"\begin{wrBox}" + required() + "\n" + r"\end{wrBox}",
        }[pick]()
        out.append(line if rnd.random() < 0.9 else "% " + line.replace("\n", "\n% "))
    return "\n".join(out)


@pytest.mark.parametrize(
    "name,body", [("hand", HAND), ("generated-1", generated(1, 150)), ("generated-2", generated(2, 150))]
)
async def test_the_calls_a_document_writes_are_the_calls_tex_makes(compiler, name, body):  # noqa: F811
    text = (
        "\\documentclass{article}\n\\usepackage{wr}\n\\usepackage{xparse}\n\\begin{document}\n"
        + body
        + "\n\\end{document}\n"
    )
    stubs = list(CLASSES.values())
    made = await calls_by_tex(compiler, text, stubs, dict(pkg.files()))
    parsed = parse_calls(text.split("\\begin{document}", 1)[1], CLASSES)
    assert not [p for p in parsed if isinstance(p, Unreadable)]
    assert [c.probe_value() for c in made] == [p.call.probe_value() for p in parsed if isinstance(p, ParsedCall)]


async def test_the_calls_of_a_table_are_the_calls_tex_makes(compiler):  # noqa: F811
    slots = PreambleSlots(after_package=(Raw(r"\usepackage{xcolor}\usepackage{tabularray}"),))
    plan = rows_pkg.plan(Document(entries(), preamble=slots))
    classes = _classes((rows_pkg,), ())
    try:
        made = await calls_by_tex(compiler, plan.text, list(classes.values()), dict(rows_pkg.files()))
    except CompileError as exc:
        if exc.code == "TM-X013":
            pytest.skip(str(exc))
        raise
    parsed = parse_calls(plan.text, classes)
    assert [c.probe_value() for c in made] == [p.call.probe_value() for p in parsed if isinstance(p, ParsedCall)]
