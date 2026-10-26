"""The constructive emitter (§21): `Group`, `Seq`, `Cs`, `Lit`, with holes and references inside."""

import enum

import pytest
from hypothesis import (
    given,
    strategies as st,
)
from test_texmodel_build.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.body import Cs, Group, Hole, Lit, Seq, Whitespace, inline_text
from texmodel.components import Command
from texmodel.document import Document
from texmodel.package import Package
from texmodel.types import Choice, Raw, Text, balanced

from .test_document import refused


def sty(body, **package) -> str:
    pkg = Package("emit-demo", prefix="em", **package)

    @pkg.command
    class Item(Command):
        """An item."""

        text: Text

        def body(self):  # noqa: ARG002
            return body

    return pkg.render()


def test_pieces_render_as_the_tex_they_stand_for():
    assert inline_text(Seq(Cs("textbf"), Group(Hole("text"))), str) == r"\textbf{#text}"
    assert inline_text(Group(Cs("bfseries"), Hole("text")), str) == r"{\bfseries #text}"
    assert inline_text(Group(Cs("a"), Cs("b"), Group(), Lit("x")), str) == r"{\a\b{}x}"
    assert inline_text(Seq(Cs("x"), Seq(Lit("y"))), str) == r"\x y"  # the next text could continue the name
    assert inline_text(Seq(Seq(Cs("x")), Raw("y")), str) == r"\x y"
    assert inline_text(Seq(Cs("x"), Seq(), Cs("y")), str) == r"\x\y"
    assert inline_text(Seq(Cs("x"), Group(Lit("y"))), str) == r"\x{y}"
    assert inline_text(Lit("50% of #1 & _a_"), str) == r"50\% of \#1 \& \_a\_"


def test_a_constructive_body_is_one_line_per_piece_in_the_packages_policy():
    out = sty([Cs("par"), Group(Cs("bfseries"), Hole("text")), Lit("a & b")], whitespace=Whitespace.TRIM)
    assert "{%\n\\par%\n{\\bfseries #1}%\n" + r"a \& b%" + "\n}" in out
    assert "{%\n\\par\n{\\bfseries #1}\n" + r"a \& b" + "\n}" in sty(
        [Cs("par"), Group(Cs("bfseries"), Hole("text")), Lit("a & b")]
    )


def test_a_hash_in_a_lit_is_a_character_not_a_hole():
    out = sty([Lit("#text and "), Hole("text")])
    assert "{%\n" + r"\#text and " + "\n#1\n}" in out
    assert r"\#1" in sty(Seq(Lit("#1"), Hole("text")))  # not refused as `#1`, not rewritten


def test_a_hole_that_is_not_a_field_is_still_refused_inside_a_group():
    with refused("TM-M009"):
        sty(Group(Hole("nope")))


@pytest.mark.parametrize("name", ["", "a b", "a1", "a_b", "\\par", "par*", "é"])
def test_a_control_word_has_letters_and_at_only(name):
    with refused("TM-M027"):
        Cs(name)
    assert Cs("makeatletter").name == "makeatletter" and Cs("@ifnextchar").name == "@ifnextchar"


pieces = st.recursive(
    st.one_of(
        st.builds(Cs, st.from_regex(r"[A-Za-z@]{1,6}", fullmatch=True)),
        st.builds(Lit, st.text(max_size=8)),
        st.builds(Hole, st.just("text")),
        st.builds(Raw, st.sampled_from(["", "x", r"\relax", "{a}", r"\{"])),
    ),
    lambda inner: st.one_of(
        st.builds(lambda xs: Group(*xs), st.lists(inner, max_size=4)),
        st.builds(lambda xs: Seq(*xs), st.lists(inner, max_size=4)),
    ),
    max_leaves=12,
)


@given(pieces)
def test_any_nesting_is_balanced_by_construction(piece):
    assert balanced(inline_text(piece, str))


def test_a_reference_inside_a_group_makes_its_package_a_requirement():
    base = Package("base-demo", prefix="bs")

    @base.command
    class Fact(Command):
        """A fact."""

        body = "#text"
        text: Text

    user = Package("user-demo", prefix="us")

    @user.command
    class Entry(Command):
        """Calls Fact inside a group."""

        text: Text

        def body(self):  # noqa: ARG002
            return Group(Seq(Fact.call(Hole("text")), Lit("!")))

    assert user.depends_on == (base,) and r"\RequirePackage{base-demo}" in user.render()
    assert r"{\bsFact{#1}!}" in user.render()


@enum.unique
class Level(Choice):
    """A level: each member is the macro the document defines for it."""

    LOW = Raw(r"\lvLow")
    HIGH = Raw(r"\lvHigh")


def level_package():
    pkg = Package("level-demo", prefix="em")

    @pkg.command
    class Rating(Command):
        """Writes the name of its level to the log."""

        level: Level

        def body(self):  # noqa: ARG002
            for member in Level:  # one branch per member, chosen when TeX expands the call
                yield Seq(
                    Cs("ifx"),
                    Hole("level"),
                    member.value,
                    Group(Cs("typeout"), Group(Lit(f"texmodel:probe:r={member.name}"))),
                    Cs("fi"),
                )

    return pkg, Rating


def test_a_choice_loop_emits_one_branch_per_member():
    pkg, _ = level_package()
    text = pkg.render()
    assert r"\ifx #1\lvLow{\typeout{texmodel:probe:r=LOW}}\fi" in text
    assert r"\ifx #1\lvHigh{\typeout{texmodel:probe:r=HIGH}}\fi" in text


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_the_branch_of_the_chosen_member_runs_when_tex_expands_it(compiler, tmp_path):  # noqa: F811
    pkg, rating = level_package()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "level-demo.sty").write_text(pkg.render(), encoding="utf-8")
    tex = pkg.document(Document(rating(level=Level.HIGH), preamble=None)).replace(
        r"\begin{document}", "\\def\\lvLow{L}\\def\\lvHigh{H}\n\\begin{document}.\n"
    )
    (tmp_path / "src" / "d.tex").write_text(tex, encoding="utf-8")
    result = compiler.compile(tmp_path / "src" / "d.tex", tmp_path / "out")
    assert result.ok, [(x.message, x.code) for x in result.diagnostics]
    assert result.probes == {"r": "HIGH"}
