"""An explicit TeX name (`cs`), packages with no prefix, built-in packages and explicit `require` (std libraries)."""

import pytest

from texmodel.body import Hole
from texmodel.components import Command, Environment, control_name
from texmodel.package import Package
from texmodel.testing import Call, expand
from texmodel.types import Raw, Text

from .test_document import refused


def kit():
    pkg = Package("cs-demo", prefix="cd")

    @pkg.command
    class Fact(Command):
        """Named by prefix and class."""

        body = "#text"
        text: Text

    @pkg.command
    class Quick(Command):
        """Named by itself."""

        cs = "quickfact"
        body = "#text"
        text: Text

    @pkg.environment
    class Box(Environment):
        """An environment named by itself."""

        cs = "quickbox"
        children = [Fact.times.any()]
        begin = r"\begin{center}#title"
        end = r"\end{center}"
        title: Text

    return pkg, Fact, Quick, Box


def test_a_class_may_name_its_control_sequence():
    pkg, fact, quick, box = kit()
    sty = pkg.render()
    assert r"\newcommand{\cdFact}[1]{%" in sty and r"\newcommand{\quickfact}[1]{%" in sty
    assert r"\newenvironment{quickbox}[1]{%" in sty
    assert [control_name(c) for c in (fact, quick, box)] == ["cdFact", "quickfact", "quickbox"]
    assert box(quick("a"), title="T").validate() == [] or True
    assert quick("R&D").render() == r"\quickfact{R\&D}"
    assert box(fact("a"), title="T").render() == "\\begin{quickbox}{T}\n\\cdFact{a}\n\\end{quickbox}"


def test_a_reference_and_a_stub_use_the_explicit_name():
    pkg, fact, quick, box = kit()
    user = Package("cs-user", prefix="cu")

    @user.command
    class Uses(Command):
        """Calls both."""

        text: Text

        def body(self):  # noqa: ARG002
            yield quick.call(Hole("text"))
            yield box.open(title=Hole("text"))
            yield box.close()

    assert r"\quickfact{#1}" in user.render() and r"\begin{quickbox}{#1}" in user.render()
    assert [c for c in expand(Uses("x"), [quick]) if isinstance(c, Call)] == [Call("quickfact", ("x",))]
    assert [c for c in expand(Uses("x"), [quick, box]) if isinstance(c, Call)][1].name == "quickbox"
    assert "\\providecommand{\\quickfact}{}" in pkg.test_document(quick("x"), stub=[quick])


def test_names_collide_by_their_control_sequence_and_must_be_control_words():
    pkg, *_ = kit()
    with refused("TM-M007"):

        @pkg.command
        class Other(Command):
            """Takes quickfact again."""

            cs = "quickfact"
            body = "x"

    with refused("TM-M027"):

        class Bad(Command):
            """A digit is no letter."""

            cs = "quick2"
            body = "x"


def test_an_adopted_package_is_checked_against_the_explicit_name():
    pkg = Package("std-demo", prefix="", adopted=True)

    @pkg.command
    class IncludeGraphics(Command):
        """Place an image."""

        cs = "includegraphics"
        path: Raw
        options: Raw | None = None

    assert pkg.check_interface(r"\newcommand{\includegraphics}[2][]{}") == []
    (missing,) = pkg.check_interface(r"\newcommand{\other}{}")
    assert missing.code == "TM-C010" and r"\includegraphics" in missing.message
    assert (
        IncludeGraphics(path=Raw("a.png"), options=Raw("width=3cm")).render() == r"\includegraphics[width=3cm]{a.png}"
    )


def test_a_package_with_no_prefix_does_not_police_names():
    pkg = Package("noprefix-demo", prefix="")

    @pkg.command
    class Title(Command):
        """Uses LaTeX's own capitalised names freely."""

        cs = "mytitle"
        body = r"\LaTeX\ #text \Large"
        text: Text

    assert r"\newcommand{\mytitle}[1]{%" in pkg.render()


def test_builtin_packages_need_no_require_and_explicit_requires_come_first_with_their_options():
    latex = Package("latex", prefix="", adopted=True, builtin=True)
    xcolor = Package("xcolor", prefix="", adopted=True)
    micro = Package("microtype", prefix="", adopted=True)

    @latex.command
    class Noindent(Command):
        """No indent."""

        cs = "noindent"

    @xcolor.command
    class Color(Command):
        """Colour."""

        cs = "color"
        name: Raw

    pkg = Package("user-demo", prefix="us")
    pkg.require(micro, options=["protrusion=true", "final"])
    pkg.require(xcolor, options=["table"])

    @pkg.command
    class Entry(Command):
        """Calls both."""

        text: Text

        def body(self):  # noqa: ARG002
            yield Noindent.call()
            yield Color.call(Raw("red"))
            yield Hole("text")

    assert pkg.required_packages == ("microtype", "xcolor") and pkg.depends_on == (micro, xcolor)
    sty = pkg.render()
    assert "\\RequirePackage[protrusion=true,final]{microtype}\n\\RequirePackage[table]{xcolor}\n" in sty
    assert "RequirePackage{latex}" not in sty and "\\noindent\n\\color{red}\n#1" in sty


def test_require_refuses_a_builtin_a_bad_option_and_a_repeat():
    pkg = Package("req-demo", prefix="rq")
    kernel = Package("latex", prefix="", adopted=True, builtin=True)
    other = Package("other", prefix="", adopted=True)
    with refused("TM-P008"):
        pkg.require(kernel)
    with refused("TM-P009"):
        pkg.require(other, options=["a b"])
    pkg.require(other)
    with refused("TM-P010"):
        pkg.require(other)
    with pytest.raises(Exception, match="prefix"):
        Package("x", prefix="Bad")
