"""`ColourName`: a colour or an xcolor expression, built from a colour value, and checked against its package."""

import pytest

from texmodel._internal.bodies import body_of
from texmodel.components import Command, Environment, Passthrough, Value
from texmodel.errors import DeclarationError
from texmodel.ext.colourspace import ColourPair, ColourSpace, Dual
from texmodel.ext.plates import K, Plate
from texmodel.interface import ColourName
from texmodel.package import Package
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import CMYK, Colour, Raw, Text

brand = Package("acme-brand", prefix="ab")
series = Package("acme-series", prefix="as", base=brand)


@brand.value
class Ink(Value[Colour]):
    """Text ink."""

    plates = {Plate.K}
    default = K(0.95)


@brand.value
class Paper(Value[Colour]):
    """The paper, tinted by the black plate only."""

    plates = {Plate.K}
    default = CMYK(0, 0, 0, 0)


brand.library(
    "extras",
    r"\definecolor{abFoil}{cmyk}{0,0.2,1,0}",
)


@series.command
class Label(Command):
    """A coloured label."""

    text: Text
    colour: ColourName
    other: ColourName | None = None
    body = r"\textcolor{#colour}{#text}#other"


def test_a_name_is_a_string_and_a_colour_value_gives_its_name():
    assert ColourName("red") == "red" and isinstance(ColourName("red"), str)
    assert ColourName(Ink) == "ab-ink" and ColourName(Paper) == "ab-paper"
    assert ColourName(Ink, tint=0.7) == "ab-ink!70" and ColourName(Ink, tint=0.375) == "ab-ink!37.5"
    assert ColourName(Ink, tint=0.7, mix=Paper) == "ab-ink!70!ab-paper"
    assert ColourName("red", tint=0.5, mix="blue") == "red!50!blue" and ColourName("red", tint=0) == "red!0"


@pytest.mark.parametrize(
    ("args", "code"),
    [
        ({"base": "two words"}, "TM-M067"),
        ({"base": "1red"}, "TM-M067"),
        ({"base": "red", "mix": "blue"}, "TM-M067"),
        ({"base": Ink, "tint": 0.5, "mix": "red"}, "TM-M068"),
        ({"base": "red", "tint": 70}, "TM-M017"),
        ({"base": "red", "tint": -0.1}, "TM-M017"),
        ({"base": int}, "TM-M066"),
    ],
)
def test_a_name_that_is_not_a_colour_is_refused(args, code):
    with pytest.raises(DeclarationError) as raised:
        ColourName(**args)
    assert raised.value.code == code


def test_names_are_the_colours_an_expression_uses():
    assert ColourName("red").names == ("red",) and ColourName("red!50").names == ("red",)
    assert ColourName("red!50!blue!20").names == ("red", "blue")
    for bad in ("red!!blue", "red!50!50", "red!150", "red!x", "red!50!"):
        with pytest.raises(DeclarationError) as raised:
            ColourName(bad)
        assert raised.value.code == "TM-M067"


def test_a_field_of_the_type_is_a_colour_name():
    body = body_of(ColourName)
    assert body is not None and body.kind.value == "ColourName"
    assert body_of(ColourName | None) == body


def violations(**fields):
    return [(v.code, v.path) for v in Label(text="x", **fields).violations()]


def test_a_colour_the_package_declares_a_library_defines_or_xcolor_names_is_known():
    assert violations(colour=ColourName(Ink)) == []  # a value of the base package
    assert violations(colour=ColourName("abFoil")) == []  # a library defines it
    assert violations(colour=ColourName("red")) == [] and violations(colour=ColourName("darkgray!50!white")) == []
    assert violations(colour=ColourName(Ink, tint=0.7, mix=Paper)) == []
    assert violations(colour="ab-ink!30", other="gray") == []  # a plain string is as good


def test_a_colour_nothing_declares_is_a_violation_at_the_field():
    assert violations(colour=ColourName("nonsense")) == [("TM-C022", "Label.colour")]
    assert violations(colour=ColourName("red!50!nonsense"), other=ColourName("ab-ink!20!other")) == [
        ("TM-C022", "Label.colour"),
        ("TM-C022", "Label.other"),
    ]
    assert violations(colour=ColourName("MidnightBlue")) == [("TM-C022", "Label.colour")]  # a dvipsnames colour
    (found,) = Label(text="x", colour=ColourName("nonsense")).violations()
    assert "nonsense" in found.message and "acme-series" in found.message


def test_an_expression_that_is_not_the_grammar_is_a_violation():
    assert violations(colour="red!!blue") == [("TM-C023", "Label.colour")]
    assert violations(colour="red!150") == [("TM-C023", "Label.colour")]


def test_the_check_runs_in_the_document_and_in_a_tree():
    with pytest.raises(ExceptionGroup):
        series.document(Label(text="x", colour=ColourName("nonsense")))
    assert r"\asLabel{x}{ab-ink!70}" in series.document(Label(text="x", colour=ColourName(Ink, tint=0.7)))

    @series.environment
    class Box(Environment):
        """A box."""

        children = [Label.times.any()]
        begin = r"\begin{center}"
        end = r"\end{center}"

    nested = Box(Label(text="x", colour=ColourName("nonsense")))
    assert [(v.code, v.path) for v in nested.violations()] == [("TM-C022", "Box/Label[0].colour")]
    assert series.document(Passthrough(Raw(r"\relax")))  # no colour argument, nothing to check


def test_a_node_outside_a_package_is_not_checked():
    class Loose(Command):
        """Not in a package."""

        text: Text
        colour: ColourName
        body = "#colour #text"

    assert Loose(text="x", colour=ColourName("nonsense")).violations() == []


def test_the_colours_of_the_dual_and_the_base_chain_are_known_too():
    pair = Package("acme-pair", prefix="ap")
    ColourSpace().declare(pair)

    @pair.value
    class Web(Value[Dual]):
        """Both builds."""

        default = ColourPair(cmyk=K(1), rgb="000000")

    @pair.command
    class Mark(Command):
        """A mark."""

        colour: ColourName
        body = r"\textcolor{#colour}{x}"

    assert Mark(colour=ColourName(Web, tint=0.5)).violations() == []
    assert [v.code for v in Mark(colour=ColourName("ab-ink")).violations()] == ["TM-C022"]  # not its base: unrelated


def test_data_reads_a_string_and_writes_one():
    doc = from_dict(series, {"content": [{"type": "Label", "text": "x", "colour": "ab-ink!70"}]})
    (label,) = doc.content
    assert isinstance(label, Label) and isinstance(label.colour, ColourName) and label.colour == "ab-ink!70"
    assert to_dict(label)["colour"] == "ab-ink!70" and type(to_dict(label)["colour"]) is str
    for bad in ("two words", "red!150", ""):
        with pytest.raises(ExceptionGroup):
            from_dict(series, {"content": [{"type": "Label", "text": "x", "colour": bad}]})
    assert json_schema(Label)["properties"]["colour"]["type"] == "string"


def test_both_ends_of_a_mix_ink_the_same_plates():
    duo = Package("acme-duo", prefix="ad", base=brand)

    @duo.value
    class Wash(Value[Colour]):
        """Two plates."""

        plates = {Plate.C, Plate.M}
        default = CMYK(0.2, 0.1, 0, 0)

    @duo.value
    class Process(Value[Colour]):
        """Any process plate."""

        default = CMYK(0.1, 0.4, 0.3, 0)

    assert ColourName(Ink, tint=0.7, mix=Paper) == "ab-ink!70!ab-paper"  # both K only
    assert ColourName(Ink, tint=0.7, mix="white") == "ab-ink!70!white"  # white inks nothing
    assert ColourName(Ink, tint=0.4, mix="black") == "ab-ink!40!black"  # xcolor's black is the K plate
    for other in (Wash, Process, "red", "gray!50"[:4] if False else "blue"):
        with pytest.raises(DeclarationError) as raised:
            ColourName(Ink, tint=0.5, mix=other)
        assert raised.value.code == "TM-M068"
    with pytest.raises(DeclarationError):
        ColourName(Wash, tint=0.5, mix=Process)  # two plates are not four


def test_an_expression_that_mixes_different_plates_is_a_violation_whoever_wrote_it():
    assert violations(colour="ab-ink!70!ab-paper") == [] and violations(colour="ab-ink!70!white") == []
    assert violations(colour="ab-ink!70!red") == [("TM-C024", "Label.colour")]
    assert violations(colour="red!50!blue") == []  # two process colours
    assert violations(colour="ab-ink!50!ab-paper!20!blue") == [("TM-C024", "Label.colour")]  # every name counts
    (found,) = Label(text="x", colour=ColourName("ab-ink!70!red")).violations()
    assert "ab-ink K" in found.message and "red C+M+Y+K" in found.message
    assert violations(colour="ab-ink!70!nonsense") == [("TM-C022", "Label.colour")]  # an unknown name has no plates yet
