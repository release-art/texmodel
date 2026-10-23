"""`describe`: a registered component as data."""

import pytest

from texmodel.components import ArgumentInfo, Command, Description, Environment, Value, describe, field
from texmodel.errors import DeclarationError
from texmodel.package import Package
from texmodel.types import CMYK, Colour, Length, Raw, Text


def test_describe_reports_each_category():
    pkg = Package("bb-demo", prefix="bb")

    @pkg.command
    class Name(Command):
        """the name"""

        name: Raw = field(doc="the subject's name")
        note: Raw | None = None

        def body(self):
            return r"\textbf{#name}#note"

    @pkg.environment
    class Box(Environment):
        """a box"""

        begin = r"\begingroup"
        end = r"\endgroup"

    @pkg.value
    class Width(Value[Length]):
        """a width"""

        default = Length("105mm")

    @pkg.value
    class Label(Value[Text]):
        """a label"""

        cs = "bbLbl"
        default = "Fun"

    @pkg.value
    class Cut(Value[Colour]):
        """a cut line"""

        default = CMYK(0, 0.4, 1, 0)
        colour_name = "bbCut"

    assert describe(Name) == Description(
        "command",
        "Name",
        "bbName",
        "the name",
        (ArgumentInfo("name", False, "the subject's name"), ArgumentInfo("note", True, None)),
        None,
        None,
        None,
    )
    assert describe(Box) == Description("environment", "Box", "bbBox", "a box", (), None, None, None)
    assert describe(Width) == Description("value", "Width", "bbWidth", "a width", (), Length, Length("105mm"), None)
    assert describe(Label).cs == "bbLbl"
    assert describe(Label).python is str
    assert describe(Cut) == Description("value", "Cut", None, "a cut line", (), Colour, CMYK(0, 0.4, 1, 0), "bbCut")


def test_describe_refuses_what_is_not_registered():
    class Loose(Command):
        """loose"""

    with pytest.raises(DeclarationError) as failed:
        describe(Loose)
    assert failed.value.code == "TM-M019"
    pkg = Package("bb-demo", prefix="bb")
    made = pkg.make_command("Made", "made", body="x")
    assert describe(made).cs == "bbMade"
    with pytest.raises(DeclarationError) as failed:
        describe(type("Odd", (), {"__tm_prefix__": "bb"}))
    assert failed.value.code == "TM-M019"
