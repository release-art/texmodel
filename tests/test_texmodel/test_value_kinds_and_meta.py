"""Colour names, optional-argument defaults, toggles, bare lengths and metadata."""

import pytest

from texmodel.components import Command, Value, field
from texmodel.errors import DeclarationError
from texmodel.interface import arg
from texmodel.package import Package
from texmodel.spec import json_schema
from texmodel.std.etoolbox import Toggle
from texmodel.types import RGB, Colour, Length, Raw, Text


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
