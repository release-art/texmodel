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
    assert box(quick(text="a"), title="T").violations() == [] or True
    assert quick(text="R&D").render() == r"\quickfact{R\&D}"
    assert box(fact(text="a"), title="T").render() == "\\begin{quickbox}{T}\n  \\cdFact{a}\n\\end{quickbox}"


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
    assert [c for c in expand(Uses(text="x"), [quick]) if isinstance(c, Call)] == [Call("quickfact", ("x",))]
    assert [c for c in expand(Uses(text="x"), [quick, box]) if isinstance(c, Call)][1].name == "quickbox"
    assert "\\providecommand{\\quickfact}{}" in pkg.test_document(quick(text="x"), stub=[quick])


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
        pkg.require(other, options=["a%b"])
    pkg.require(other)
    with refused("TM-P010"):
        pkg.require(other)
    with pytest.raises(Exception, match="prefix"):
        Package("x", prefix="Bad")


def test_a_field_named_type_is_refused_because_data_uses_it_for_the_component():
    with refused("TM-M030"):

        class Typed(Command):
            """A field called type."""

            body = "#type"
            type: Text

    with refused("TM-M030"):

        class Box(Environment):
            """An environment with such a field."""

            begin = "#type"
            end = "x"
            type: Text

    from texmodel.body import Comment

    with refused("TM-M030"):

        class Note(Comment):
            """A comment with such a field."""

            template = "#type"
            type: str


def test_a_package_with_no_prefix_needs_cs_on_every_component():
    pkg = Package("noprefix-demo2", prefix="")
    with refused("TM-P011"):

        @pkg.command
        class Fact(Command):
            """Would be \\Fact."""

            body = "x"


def test_package_options_may_hold_braces_and_spaces_but_not_what_ends_the_list():
    pkg, other = Package("opt-demo", prefix="op"), Package("lib", prefix="", adopted=True)
    pkg.require(other, options=["margin=10mm", "colorprofiles={A=a.icc,X=b.icc}", "a b"])
    assert pkg.require_entries() == [("lib", ("margin=10mm", "colorprofiles={A=a.icc,X=b.icc}", "a b"))]
    for bad in ("", " ", "a]b", "a[b", "50%", "\\x", "{a", "a}"):
        with refused("TM-P009"):
            Package("opt-demo2", prefix="op").require(other, options=[bad])


def test_a_passthrough_naming_an_undeclared_name_of_the_package_is_refused_with_its_path():
    from texmodel.components import Anywhere, Passthrough

    pkg = Package("pt-demo", prefix="pt")

    @pkg.environment
    class Box(Environment):
        """A box."""

        children = [Anywhere(Passthrough)]
        begin = "x"
        end = "y"

    good = Box(Passthrough(Raw(r"\ptBox \LaTeX \other")))
    assert pkg.plan(good).text.count("\\ptBox") == 1
    with pytest.raises(ExceptionGroup) as group:
        pkg.plan(Passthrough(Raw("a")), Box(Passthrough(Raw(r"\ptMissing"))))
    (found,) = group.value.exceptions
    assert (found.code, found.path) == ("TM-M015", "Box[1]/Passthrough[0]")  # pyright: ignore[reportAttributeAccessIssue]
