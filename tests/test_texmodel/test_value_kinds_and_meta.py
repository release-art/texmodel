"""Colour names, optional-argument defaults, toggles, bare lengths and metadata."""

import pytest

from texmodel.components import Command, Value, field
from texmodel.errors import DeclarationError
from texmodel.interface import arg
from texmodel.package import Package
from texmodel.spec import json_schema
from texmodel.std.etoolbox import Toggle
from texmodel.types import RGB, Colour, Length, Name, Raw, Text


def test_colour_name_replaces_the_derived_name():
    p = Package("p", prefix="ac")

    @p.value
    class AcInk(Value[Colour]):
        """Ink."""

        colour_name = "acInk"
        default = RGB(0, 0, 0)

    assert "\\definecolor{acInk}{rgb}" in p.render(version="0.1.0")


def test_colour_name_is_for_colours_only():
    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-M012"):

        class L(Value[Length]):
            """L."""

            colour_name = "x"
            default = Length("1mm")


def test_optional_argument_default():
    p = Package("p", prefix="ac")

    @p.command
    class Rating(Command):
        """Rating."""

        mark: Raw | None = arg(default=Raw(r"\acMark"))
        text: Text

        def body(self):
            return r"#mark #text"

    assert "\\newcommand{\\acRating}[2][\\acMark]{" in p.render(version="0.1.0")

    @p.command
    class Scaled(Command):
        """Scaled."""

        count: int | None = arg(default=3)
        text: Text

        def body(self):
            return r"#count #text"

    assert "\\newcommand{\\acScaled}[2][3]{" in p.render(version="0.1.0")


def test_toggle_and_bare_length():
    p = Package("p", prefix="ac")

    @p.value
    class Draft(Value[Toggle]):
        """Draft."""

        default = False

    @p.value
    class Width(Value[Length]):
        """Computed later."""

    out = p.render(version="0.1.0")
    assert "\\newtoggle{acDraft}\n\\togglefalse{acDraft}" in out
    assert "\\newlength{\\acWidth}\n" in out and "\\setlength{\\acWidth}" not in out
    assert "\\RequirePackage{etoolbox}" in out


def test_meta_reaches_the_schema():
    p = Package("p", prefix="ac")

    @p.command
    class Pic(Command):
        """Pic."""

        meta = {"audience": "deck"}
        src: Text = field(doc="The file.", meta={"type": "file"})
        alt: Text | None = arg(default=None, doc="Alt text.", meta={"audience": "tools"})

        def body(self):
            return r"#src#alt"

    d = json_schema(p)["$defs"]["Pic"]
    assert d["x-audience"] == "deck"
    assert d["properties"]["src"]["description"] == "The file." and d["properties"]["src"]["x-type"] == "file"
    assert d["properties"]["alt"]["x-audience"] == "tools"


def test_a_value_can_need_a_package_of_this_project():
    helper = Package("helper", prefix="hp")

    class Needs(Value[Length]):
        """Needs helper."""

        needs_packages = (helper,)

    p = Package("p", prefix="ac")
    p.value(Needs)
    assert p.required_packages == ("helper",) and p.depends_on == (helper,)


def test_a_call_can_be_an_argument_of_another_call():
    from texmodel.body import Seq
    from texmodel.std.etoolbox import IfNumGreater
    from texmodel.std.latex import PackageError, StepCounter

    p = Package("p", prefix="ac")

    class Fact(Command, unused=("text",)):
        """A fact."""

        text: Text

        def body(self):
            fail = PackageError.call(Name("p"), Raw("Too many"), Raw("At most 3."))
            return [IfNumGreater.call(Raw(r"\value{n}"), Raw("3"), Seq(fail, StepCounter.call(Name("n"))), Raw(""))]

    p.command(Fact)
    assert "\\ifnumgreater{\\value{n}}{3}{\\PackageError{p}{Too many}{At most 3.}\\stepcounter{n}}{}" in p.render()
    assert p.depends_on[0].name == "etoolbox"

    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-M026"):
        Fact.call(StepCounter.call(Name("n")))  # a Text argument is text, not a call


def test_a_counting_rule_is_a_macro_parametrised_by_its_counter():
    from texmodel.body import Hole, Lit, Ref, Seq
    from texmodel.components import Environment
    from texmodel.std.etoolbox import IfNumGreater, IfNumLess
    from texmodel.std.latex import CounterValue, PackageError, SetCounter, StepCounter

    p = Package("p", prefix="ac")

    def too(word: str) -> Ref:
        message = Seq(Lit(f"Too {word} "), Hole("what"), Lit(" on one card"))
        return PackageError.call(Name("p"), message, Raw("See the brand rules."))

    @p.command
    class CountAtMost(Command):
        """Count one more of a region, and fail past its limit."""

        counter: Raw
        limit: Raw
        what: Raw

        def body(self):
            return [
                StepCounter.call(Hole("counter")),
                IfNumGreater.call(CounterValue.call(Hole("counter")), Hole("limit"), too("many"), Raw("")),
            ]

    @p.command
    class CountAtLeast(Command):
        """Fail when a region has fewer than its minimum."""

        counter: Raw
        limit: Raw
        what: Raw

        def body(self):
            return [
                IfNumLess.call(CounterValue.call(Hole("counter")), Hole("limit"), too("few"), Raw("")),
            ]

    @p.command
    class Fact(Command, unused=("text",)):
        """A fact."""

        text: Text

        def body(self):
            return [CountAtMost.call(Raw("acFacts"), Raw("3"), Raw("facts")), r"#text"]

    @p.environment
    class Card(Environment):
        """A card."""

        children = [Fact.times(2, 3)]

        def begin(self):
            return [SetCounter.call(Name("acFacts"), Raw("0"))]

        def end(self):
            return [CountAtLeast.call(Raw("acFacts"), Raw("2"), Raw("facts"))]

    out = p.render(version="0.1.0")
    assert "\\newcommand{\\acCountAtMost}[3]{" in out
    assert "\\ifnumgreater{\\value{#1}}{#2}{\\PackageError{p}{Too many #3 on one card}{See the brand rules.}}{}" in out
    assert "\\acCountAtMost{acFacts}{3}{facts}" in out and "\\acCountAtLeast{acFacts}{2}{facts}" in out
