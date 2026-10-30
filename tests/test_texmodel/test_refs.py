"""Typed references in bodies: `call`, `open`, `close`, holes, packages that follow."""

import pytest

from texmodel.body import Hole, RefKind, TexRaw, Whitespace
from texmodel.components import Command, Environment
from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.package import Package
from texmodel.types import Choice, Raw, Text

from .test_document import refused


def base():
    pkg = Package("base-demo", prefix="bs")

    @pkg.command
    class Fact(Command):
        """A fact."""

        body = "#text"
        text: Text

    @pkg.command
    class Slot(Command):
        """A slot with an optional label."""

        body = "#text #label"
        text: Text
        label: Text | None = None

    @pkg.command
    class Image(Command):
        """A picture."""

        body = "#path"
        path: Raw

    @pkg.environment
    class Box(Environment):
        """A box."""

        children = [Fact.times.any()]
        begin = r"\\begin{center}#title"
        end = r"\\end{center}"
        title: Text

    return pkg, Fact, Slot, Image, Box


def test_a_call_writes_the_component_with_holes_raws_and_escaped_text():
    _, fact, slot, image, _ = base()
    assert fact.call(Hole("text")).values == (Hole("text"),)
    pkg = Package("user-demo", prefix="us")

    @pkg.command
    class Entry(Command):
        """Calls others."""

        text: Text

        def body(self):  # noqa: ARG002
            yield fact.call(Hole("text"))
            yield slot.call("R&D", label="a]b")
            yield slot.call(Hole("text"))
            yield image.call(Raw("a_b.jpg"))

    assert pkg.render().splitlines()[-6:-1] == [
        r"\newcommand{\usEntry}[1]{%",
        r"\bsFact{#1}",
        r"\bsSlot[{a]b}]{R\&D}",
        r"\bsSlot{#1}",
        r"\bsImage{a_b.jpg}",
    ]


def test_an_environment_is_opened_and_closed_by_reference():
    _, fact, _, _, box = base()
    pkg = Package("user-demo", prefix="us")

    @pkg.environment
    class Panel(Environment):
        """Wraps a box."""

        children = [fact.times.any()]
        begin = box.open(title=Hole("title"))
        end = box.close()
        title: Text

    assert r"\begin{bsBox}{#1}" in pkg.render() and r"\end{bsBox}" in pkg.render()
    assert box.open(title="x").kind is RefKind.OPEN and box.close().kind is RefKind.CLOSE


def test_a_target_in_another_package_makes_it_a_requirement_once_and_sorted():
    _, fact, slot, _, _ = base()
    other = Package("alpha-demo", prefix="al")

    @other.command
    class Mark(Command):
        """A mark."""

        body = "#text"
        text: Text

    pkg = Package("user-demo", prefix="us")

    @pkg.command
    class A(Command):
        """Calls two packages."""

        text: Text

        def body(self):  # noqa: ARG002
            return [fact.call(Hole("text")), slot.call(Hole("text")), Mark.call(Hole("text"))]

    assert pkg.required_packages == ("alpha-demo", "base-demo")
    assert pkg.render().count(r"\RequirePackage{base-demo}") == 1
    assert pkg.render().index("alpha-demo") < pkg.render().index("base-demo")
    assert tuple(p.name for p in pkg.depends_on) == ("base-demo", "alpha-demo")


def test_an_adopted_package_can_be_called_and_a_call_in_the_same_package_needs_no_require():
    adopted = Package("hand-written", prefix="hw", adopted=True)

    @adopted.command
    class Mark(Command):
        """Hand-written."""

        text: Text

    pkg = Package("user-demo", prefix="us")

    @pkg.command
    class Own(Command):
        """Own."""

        body = "#text"
        text: Text

    @pkg.command
    class Wrap(Command):
        """Calls both."""

        text: Text

        def body(self):  # noqa: ARG002
            return [Own.call(Hole("text")), Mark.call(Hole("text"))]

    out = pkg.render()
    assert r"\RequirePackage{hand-written}" in out and r"\usOwn{#1}" in out and r"\hwMark{#1}" in out
    assert pkg.depends_on == (adopted,)


def test_arguments_are_checked_when_the_piece_is_built():
    _, fact, slot, _, box = base()
    for build in (
        lambda: fact.call(),
        lambda: fact.call("a", "b"),
        lambda: fact.call("a", label="x"),
        lambda: slot.call(3),  # type: ignore[arg-type]
        lambda: slot.call("a", label=3),  # type: ignore[arg-type]
        lambda: box.open(),
        lambda: box.open(title=3),  # type: ignore[arg-type]
    ):
        with refused("TM-M026"):
            build()


def test_a_choice_member_is_a_valid_argument():
    import enum

    @enum.unique
    class Kind(Choice):
        A = Raw(r"\alpha")

    pkg = Package("user-demo", prefix="us")

    @pkg.command
    class Mark(Command):
        """A mark."""

        body = "#kind"
        kind: Kind

    caller = Package("caller-demo", prefix="ca")

    @caller.command
    class Use(Command):
        """Uses it."""

        text: Text

        body = [Mark.call(Kind.A), TexRaw("#text")]

    assert r"\usMark{\alpha}" in caller.render()


def test_the_target_must_be_registered_before_the_body_that_calls_it():
    class Loose(Command):
        """Not registered."""

        body = "x"

    pkg = Package("user-demo", prefix="us")
    with refused("TM-M019"):

        @pkg.command
        class Caller(Command):
            """Calls it."""

            body = [Loose.call()]


def test_a_reference_follows_the_policy_of_the_package_or_its_own():
    _, fact, *_ = base()
    for pkg_ws, ref, expected in (
        (Whitespace.KEEP, fact.call(Hole("text")), r"\bsFact{#1}"),
        (Whitespace.TRIM, fact.call(Hole("text")), r"\bsFact{#1}%"),
        (Whitespace.KEEP, fact.call(Hole("text")).with_whitespace(Whitespace.TRIM), r"\bsFact{#1}%"),
    ):
        pkg = Package("user-demo", prefix="us", whitespace=pkg_ws)

        @pkg.command
        class Entry(Command):
            """Entry."""

            text: Text

            body = [ref]

        assert pkg.render().rstrip().splitlines()[-2] == expected


def test_packages_that_require_each_other_are_refused_when_rendered():
    a, b = Package("pack-a", prefix="pa"), Package("pack-b", prefix="pb")

    @a.command
    class W(Command):
        """A's."""

        body = "x"

    @b.command
    class Y(Command):
        """B's, calls A."""

        body = [W.call()]

    @a.command
    class X(Command):
        """A's, calls B."""

        body = [Y.call()]

    with refused("TM-P007"):
        a.render()
    with refused("TM-P007"):
        b.render()


def test_an_adopted_package_declares_what_it_needs_and_those_load_before_it():
    colours = Package("hand-colours", prefix="", adopted=True)
    tables = Package("hand-tables", prefix="", adopted=True, requires=[colours])
    grids = Package("hand-grids", prefix="", adopted=True, requires=[tables])

    @grids.command
    class Cell(Command):
        """A cell."""

        cs = "gridcell"
        text: Text

    pkg = Package("user-grid", prefix="ug")

    @pkg.command
    class Wrap(Command):
        """Calls a cell."""

        text: Text

        def body(self):  # noqa: ARG002
            return [Cell.call(Hole("text"))]

    out = pkg.render()
    order = [out.index(rf"\RequirePackage{{{n}}}") for n in ("hand-colours", "hand-tables", "hand-grids")]
    assert order == sorted(order) and out.count("hand-colours") == 1
    assert [n for n, _ in grids._load(set(), ("opt",))] == ["hand-colours", "hand-tables", "hand-grids"]  # noqa: SLF001
    lines = grids.plan(Cell(text="x")).text.splitlines()
    assert lines[2:5] == [r"\usepackage{hand-colours}", r"\usepackage{hand-tables}", r"\usepackage{hand-grids}"]


def test_a_required_adopted_package_keeps_its_options_and_a_repeat_of_a_need_is_loaded_once():
    colours = Package("hand-colours", prefix="", adopted=True)
    tables = Package("hand-tables", prefix="", adopted=True, requires=[colours])
    pkg = Package("user-table", prefix="ut")
    pkg.require(colours, options=["table"])
    pkg.require(tables, options=["x"])
    assert pkg.require_entries() == [("hand-colours", ("table",)), ("hand-tables", ("x",))]
    for bad, code in ((lambda: Package("a", prefix="", requires=[Package("k", prefix="", builtin=True)]), "TM-P008"),):
        with pytest.raises(DeclarationError) as raised:
            bad()
        assert raised.value.code == code
    with pytest.raises(DeclarationError) as raised:
        Package("b", prefix="", requires=[colours, colours])
    assert raised.value.code == "TM-P010"


def test_a_package_two_others_need_is_loaded_once_by_the_first_call():
    shared = Package("hand-shared", prefix="", adopted=True)
    left = Package("hand-left", prefix="", adopted=True, requires=[shared])
    right = Package("hand-right", prefix="", adopted=True, requires=[shared])
    top = Package("hand-top", prefix="", adopted=True, requires=[left, right])
    assert [n for n, _ in top._load(set())] == ["hand-shared", "hand-left", "hand-right", "hand-top"]  # noqa: SLF001
    assert top.plan(Document()).text.count(r"\usepackage{hand-shared}") == 1

    pkg = Package("user-diamond", prefix="ud")
    pkg.require(left)
    pkg.require(right)
    assert [n for n, _ in pkg.require_entries()] == ["hand-shared", "hand-left", "hand-right"]
