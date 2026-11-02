"""The calls read from a document's tokens are the calls TeX makes: one compile with the stubs, compared."""

import random

import pytest
from test_texmodel.test_calls import CLASSES, pkg

from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401
from texmodel._internal.calls import ParsedCall, Unreadable, parse_calls
from texmodel.run import hand_edits

pytestmark = [pytest.mark.tex, pytest.mark.timeout(300)]

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
    made = await hand_edits._calls(compiler, text, stubs, dict(pkg.files()))
    parsed = parse_calls(text.split("\\begin{document}", 1)[1], CLASSES)
    assert not [p for p in parsed if isinstance(p, Unreadable)]
    assert [c.probe_value() for c in made] == [p.call.probe_value() for p in parsed if isinstance(p, ParsedCall)]
