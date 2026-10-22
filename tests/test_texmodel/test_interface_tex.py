"""Macro interfaces through TeX: the xparse definitions texmodel writes, the calls it writes for them, and key lists
read by real key libraries. Verification is by compiling; nothing here parses TeX."""

import enum
import re

import pytest
from test_texmodel_build.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.components import Command
from texmodel.interface import PAREN, SQUARE, Flag, Star, Switch, arg
from texmodel.keys import KEYVAL, L3KEYS, PGFKEYS, XKEYVAL
from texmodel.keyvals import KeyVals, key
from texmodel.package import Package, PreambleSlots
from texmodel.testing import Call, expand
from texmodel.types import Choice, Length, Raw, Text
from texmodel_build.testkit import run_probes

pytestmark = [pytest.mark.tex, pytest.mark.timeout(300)]

COUNTER = PreambleSlots(after_package=(Raw(r"\newcount\tmN"),))
LOG = r"\global\advance\tmN by 1 \typeout{texmodel:probe:r\the\tmN="


def numbered(found):
    return [
        m.value for _, m in sorted((int(m.name.removeprefix("r")), m) for m in found if re.fullmatch(r"r\d+", m.name))
    ]


def demo():
    pkg = Package("xp-demo", prefix="xp", version="1.0.0", date="2026/10/22")

    @pkg.command
    class Two(Command):
        """Two optional arguments and a required one."""

        a: Text | None = arg(SQUARE, default=None, fill="")
        b: Text | None = arg(SQUARE, default=None)
        c: Text

        def body(self):
            return LOG + "<#a|#b|#c>}"

    @pkg.command
    class Heading(Command):
        """A starred command with an optional short title."""

        starred: Star = arg(default=False)
        short: Text | None = arg(SQUARE, default=None)
        title: Text

        def body(self):
            return LOG + r"<\IfBooleanTF{#starred}{star}{plain}|#short|#title>}"

    @pkg.command
    class Put(Command):
        """A required argument in parentheses."""

        at: tuple[int, int] = arg(PAREN)
        text: Text

        def body(self):
            return LOG + "<#at|#text>}"

    return pkg, Two, Heading, Put


def test_xparse_definitions_receive_the_arguments_texmodel_writes():
    pkg, two, heading, put = demo()
    sty = pkg.render()
    assert r"\NewDocumentCommand{\xpTwo}{O{}O{}m}" in sty and r"\NewDocumentCommand{\xpHeading}{sO{}m}" in sty
    assert r"\NewDocumentCommand{\xpPut}{r()m}" in sty


def test_real_xparse_bodies_read_what_the_calls_say(compiler):  # noqa: F811
    pkg, two, heading, put = demo()
    nodes = [
        two("x"),
        two("x", b="y"),
        two("x", a="w", b="y"),
        heading("T"),
        heading("T", starred=True),
        heading("T", short="S"),
        heading("T", starred=True, short="S"),
        put(at=(1, 2), text="t"),
    ]
    tex = pkg.test_document(*nodes, preamble=COUNTER)
    got = numbered(run_probes(compiler, tex, {"xp-demo.sty": pkg.render()}))
    assert got == [
        "<||x>",
        "<|y|x>",
        "<w|y|x>",
        "<plain||T>",
        "<star||T>",
        "<plain|S|T>",
        "<star|S|T>",
        "<1,2|t>",
    ]


def test_stubs_log_xparse_calls_as_the_fast_tier_says(compiler):  # noqa: F811
    pkg, two, heading, put = demo()
    nodes = [two("x", b="y"), heading("T", starred=True, short="S"), heading("U"), put(at=(1, 2), text="t")]
    stubs = [two, heading, put]
    tex = pkg.test_document(*nodes, stub=stubs)
    found = run_probes(compiler, tex, {"xp-demo.sty": pkg.render()})
    got = [
        Call.parse(v)
        for _, v in sorted((int(m.name.removeprefix("call")), m.value) for m in found if m.name.startswith("call"))
    ]
    assert got == [c for n in nodes for c in expand(n, stubs) if isinstance(c, Call)]


# --- key lists read by real libraries ---------------------------------------------------------------------------------

CORPUS = ["plain", "a,b", "a=b", "x]y", " lead", "trail ", "", "a b c", "[x]", "(1,2)", "1 , 2"]


@pytest.mark.parametrize(
    ("rules", "preamble", "define", "setter"),
    [
        (PGFKEYS, r"\usepackage{pgfkeys}", r"\pgfkeys{/tm/title/.store in=\tmtitle}", r"\pgfkeys{/tm/.cd,LIST}"),
        (
            XKEYVAL,
            r"\usepackage{xkeyval}",
            r"\makeatletter\define@key{tm}{title}{\def\tmtitle{#1}}\makeatother",
            r"\setkeys{tm}{LIST}",
        ),
        (
            KEYVAL,
            r"\usepackage{keyval}",
            r"\makeatletter\define@key{tm}{title}{\def\tmtitle{#1}}\makeatother",
            r"\setkeys{tm}{LIST}",
        ),
        (
            L3KEYS,
            r"\usepackage{expl3}",
            r"\ExplSyntaxOn\keys_define:nn{tm}{title.tl_set:N=\tmtitle}"
            r"\cs_new_protected:Npn\tmset#1{\keys_set:nn{tm}{#1}}\ExplSyntaxOff",
            r"\tmset{LIST}",
        ),
    ],
    ids=["pgfkeys", "xkeyval", "keyval", "l3keys"],
)
def test_a_value_survives_the_library_as_one_value(compiler, rules, preamble, define, setter):  # noqa: F811
    class Titled(KeyVals, rules=rules):
        title: Text | None = None

    rendered = [Titled(title=v).render() for v in CORPUS]
    body = "\n".join(
        setter.replace("LIST", r) + f"\\typeout{{texmodel:probe:v{i}=[\\tmtitle]}}" for i, r in enumerate(rendered)
    )
    tex = f"\\documentclass{{article}}\n{preamble}\n\\begin{{document}}\n{define}\n{body}\n\\null\n\\end{{document}}\n"
    found = {m.name: m.value for m in run_probes(compiler, tex)}
    got = [found[f"v{i}"] for i in range(len(CORPUS))]
    kept = (lambda v: v) if rules.edge_spaces else (lambda v: v.strip())  # l3keys trims however a value is braced
    assert got == [f"[{kept(v)}]" for v in CORPUS]


@enum.unique
class Align(Choice):
    TOP = "t"
    BOTTOM = "b"


def test_flags_switches_choices_and_optional_values_through_pgfkeys(compiler):  # noqa: F811
    class Opts(KeyVals, rules=PGFKEYS):
        max_width: Length | None = key("max width")
        center: Flag = False
        clip: Switch | None = None
        valign: Align | None = None
        rounded: Length | None = key("rounded corners")

    define = r"""
\pgfkeys{/tm/.cd,
  max width/.store in=\tmw, center/.code={\def\tmc{yes}}, clip/.store in=\tmclip,
  valign/.store in=\tmv, rounded corners/.store in=\tmr}
\def\tmc{no}
"""
    lists = [
        Opts(max_width=Length.expr(r"0.5\linewidth"), center=True, clip=False, valign=Align.TOP, rounded=Length("2pt")),
        Opts(clip=True, valign=Align.BOTTOM),
        Opts(),
    ]
    body = "\n".join(
        f"\\def\\tmc{{no}}\\def\\tmw{{-}}\\def\\tmclip{{-}}\\def\\tmv{{-}}\\def\\tmr{{-}}\\pgfkeys{{/tm/.cd,{o.render()}}}"
        f"\\typeout{{texmodel:probe:o{i}=<\\tmw|\\tmc|\\tmclip|\\tmv|\\tmr>}}"
        for i, o in enumerate(lists)
    )
    head = "\\documentclass{article}\n\\usepackage{pgfkeys}\n\\begin{document}\n"
    tex = head + define + "\n" + body + "\n\\null\n\\end{document}\n"
    found = {m.name: m.value for m in run_probes(compiler, tex)}
    assert found == {
        "o0": r"<0.5\linewidth |yes|false|t|2pt>",
        "o1": "<-|no|true|b|->",
        "o2": "<-|no|-|-|->",
    }
