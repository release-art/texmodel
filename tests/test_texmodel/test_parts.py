"""A library is a part that declares what it defines (§21a 12): the declarations are checked against its TeX."""

import types

import pytest
from typer.testing import CliRunner

from texmodel import cli
from texmodel.body import Syntax
from texmodel.components import Command
from texmodel.errors import DeclarationError
from texmodel.package import Package
from texmodel.types import Text


def fact(p: Package, lib):
    class Fact(Command):
        """A fact."""

        defined_by = lib
        text: Text

    return p.command(Fact)


def test_a_library_that_matches_its_declarations_is_clean():
    p = Package("p", prefix="ac")
    fact(p, p.library("hand", r"\newcommand{\acFact}[1]{#1}" + "\n" + r"\newcommand{\ac@helper}{x}"))
    assert p.check_parts() == []


def test_a_signature_a_missing_name_and_an_undeclared_public_name_are_reported():
    p = Package("p", prefix="ac")
    fact(p, p.library("hand", r"\newcommand{\acFact}[2]{#1#2}" + "\n" + r"\newcommand{\acStray}{x}"))
    other = Package("q", prefix="ac")
    fact(other, other.library("empty", r"\newcommand{\acOther}{x}"))
    assert [(v.code, v.path) for v in p.check_parts()] == [("TM-C011", "Fact"), ("TM-C012", "hand")]
    assert [(v.code, v.path) for v in other.check_parts()] == [("TM-C010", "Fact"), ("TM-C012", "empty")]


def test_a_name_defined_twice_is_reported_and_refuses_generation():
    p = Package("p", prefix="ac")
    p.library("one", r"\newcommand{\ac@x}{1}")
    p.library("two", r"\newcommand{\ac@x}{2}")
    p.library("three", r"\newcommand{\ac@x}{3}")
    assert [v.message for v in p.check_parts()] == [
        "\\ac@x is defined by library one and by library two",
        "\\ac@x is defined by library one and by library three",
    ]
    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-P012"):
        p.render()


def test_a_library_and_a_rendered_component_may_not_define_one_name():
    p = Package("p", prefix="ac")
    p.library("hand", r"\newcommand{\acFact}[1]{#1}")

    @p.command
    class Fact(Command):
        """A fact."""

        text: Text

        def body(self):
            return r"#text"

    assert [(v.code, v.message) for v in p.check_parts()] == [
        ("TM-C013", "\\acFact is defined by Fact and by library hand")
    ]


def test_an_expl3_library_is_not_read():
    p = Package("p", prefix="ac")
    fact(p, p.library("hand", r"\cs_new:Npn \acFact:n #1 {#1}", syntax=Syntax.EXPL3))
    assert p.check_parts() == []


def test_check_reports_the_violations_of_a_generated_package(tmp_path, monkeypatch):
    (tmp_path / "mod.py").write_text(
        "from texmodel.components import Command\nfrom texmodel.package import Package\n"
        "from texmodel.types import Text\n"
        "pkg = Package('p', prefix='ac')\nlib = pkg.library('hand', r'\\newcommand{\\acFact}[2]{#1#2}')\n"
        "@pkg.command\nclass Fact(Command):\n    '''A fact.'''\n    defined_by = lib\n    text: Text\n"
    )
    (tmp_path / "pyproject.toml").write_text('[tool.texmodel]\npackage = "mod:pkg"\noutput = "gen"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    runner = CliRunner()
    runner.invoke(cli.app, ["build"])
    result = runner.invoke(cli.app, ["check"])
    assert result.exit_code == 1 and "TM-C011 Fact" in result.stdout


def test_a_length_a_toggle_and_a_robust_command_count_as_definitions():
    p = Package("p", prefix="ac")
    p.library("one", "\\newlength{\\acGap}\n\\newtoggle{acDraft}\n\\DeclareRobustCommand{\\acBold}[1]{#1}")
    p.library("two", "\\newlength\\acGap\n\\newtoggle{acDraft}\n\\newcommand{\\acBold}{x}")
    assert [v.message for v in p.check_parts() if v.code == "TM-C013"] == [
        "\\acGap is defined by library one and by library two",
        "\\acDraft is defined by library one and by library two",
        "\\acBold is defined by library one and by library two",
    ]


def fill(template, model):
    return Package("f", prefix="ac").library("h", template, fill=model).text


def test_a_library_is_filled_from_a_model_by_type():
    import dataclasses

    import pydantic

    from texmodel.types import RGB, Length, Raw

    class Brand(pydantic.BaseModel):
        name: str
        gap: Length
        ink: RGB
        mark: Raw
        copies: int
        proof: bool

    @dataclasses.dataclass
    class Page:
        brand: Brand
        ratio: float

    brand = Brand(name="R&D 50%", gap=Length("2mm"), ink=RGB(0, 0, 0.5), mark=Raw(r"\star"), copies=3, proof=True)
    template = " | ".join(
        f"<<{n}>>" for n in "brand.name brand.gap brand.ink brand.mark brand.copies brand.proof ratio".split()
    )
    assert fill(template, Page(brand, 1.5)) == r"R\&D 50\% | 2mm | 0,0,0.5 | \star | 3 | true | 1.5"
    assert fill("<<x>>", {"x": "a_b"}) == r"a\_b"
    p = Package("p", prefix="ac")
    assert p.library("plain", "keep <<this>>").text == "keep <<this>>"  # no model, no holes


def test_a_hole_with_no_field_or_a_value_of_an_unknown_type_is_refused():
    for template, model, code in [
        ("<<x>>", {"y": 1}, "TM-M041"),
        ("<<x.y>>", {"x": 1}, "TM-M041"),
        ("<<x>>", {"x": [1]}, "TM-M040"),
    ]:
        with pytest.raises(DeclarationError, check=lambda e, code=code: e.code == code):
            fill(template, model)


def test_a_flag_a_toggle_a_length_and_a_colour_can_be_defined_by_a_library():
    from texmodel.components import Value
    from texmodel.std.etoolbox import Toggle
    from texmodel.types import Colour, Length

    p = Package("p", prefix="ac")
    lib = p.library(
        "hand",
        r"""
        \newif\ifacShow
        \newif\ifacshowcrop
        \newtoggle{acDraft}
        \newlength{\acGap}
        \definecolor{acTechCut}{cmyk}{0,1,1,0}
        \colorlet{acTint}{acTechCut!20}
        \newcounter{ac@facts}
        \newsavebox{\ac@box}
        """,
    )

    @p.value
    class Show(Value[bool]):
        """Show."""

        defined_by = lib

    @p.value
    class Crop(Value[bool]):
        """Crop; the name is lower case."""

        defined_by = lib
        cs = "acshowcrop"

    @p.value
    class Draft(Value[Toggle]):
        """Draft."""

        defined_by = lib

    @p.value
    class Gap(Value[Length]):
        """Gap."""

        defined_by = lib

    @p.value
    class TechCut(Value[Colour]):
        """Cut line."""

        defined_by = lib
        colour_name = "acTechCut"

    @p.value
    class Tint(Value[Colour]):
        """Tint."""

        defined_by = lib
        colour_name = "acTint"

    assert p.check_parts() == []
    assert p.render().count("\\newif\\ifacShow") == 1  # the library's own; the value renders nothing


def test_a_value_a_library_does_not_define_is_reported_and_a_second_definition_is_a_duplicate():
    from texmodel.components import Value
    from texmodel.types import Colour

    p = Package("p", prefix="ac")
    lib = p.library("hand", "\\newif\\ifacShow\n\\definecolor{acInk}{gray}{0}\n\\newcounter{n}")
    p.library("more", "\\definecolor{acInk}{gray}{1}\n\\newcounter{n}")

    @p.value
    class Missing(Value[bool]):
        """No such flag."""

        defined_by = lib

    @p.value
    class Ink(Value[Colour]):
        """Ink."""

        defined_by = lib
        colour_name = "acInk"

    @p.value
    class Paper(Value[Colour]):
        """Paper."""

        defined_by = lib
        colour_name = "acPaper"

    found = [(v.code, v.message) for v in p.check_parts()]
    assert ("TM-C010", "\\acMissingtrue is declared but library hand does not define it") in found
    assert ("TM-C010", "colour acPaper is declared but library hand does not define it") in found
    assert ("TM-C013", "colour acInk is defined by library hand and by library more") in found
    assert ("TM-C013", "counter n is defined by library hand and by library more") in found


def test_a_value_cs_and_defined_by_are_checked_when_the_class_is_defined():
    from texmodel.components import Value
    from texmodel.types import Colour, Gray, Length

    p = Package("p", prefix="ac")
    lib = p.library("hand", "\\newlength{\\acGap}")
    for base, attrs, code in [
        (Value[Length], {"defined_by": lib, "default": Length("1mm")}, "TM-M032"),
        (Value[Colour], {"cs": "acb", "default": Gray(0)}, "TM-M012"),
        (Value[Length], {"cs": "Not A Word", "default": Length("1mm")}, "TM-M027"),
    ]:
        with pytest.raises(DeclarationError, check=lambda e, code=code: e.code == code):
            types.new_class("Bad", (base,), None, lambda ns, attrs=attrs: ns.update(__doc__="Bad.", **attrs))
    other = Package("q", prefix="ac")

    class Foreign(Value[Length]):
        """Defined by another package's library."""

        defined_by = lib

    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-M033"):
        other.value(Foreign)


def test_a_flag_with_a_cs_is_declared_and_set_under_that_name():
    from texmodel.components import Value

    p = Package("p", prefix="ac")

    @p.value
    class Crop(Value[bool]):
        """Crop marks."""

        cs = "acshowcrop"
        default = True

    assert "\\newif\\ifacshowcrop\n\\acshowcroptrue" in p.render()
    assert "\\acshowcropfalse" in p.document(settings=[Crop(False)])


def test_a_definer_written_out_with_string_defines_nothing():
    from texmodel._internal.scan import scan_declarations

    text = (
        "\\typeout{\\string\\providecommand\\string\\x}\\noexpand\\newcommand\\noexpand\\y\n\\providecommand\\acReal{x}"
    )
    assert scan_declarations(text) == {"acReal": ""}
    assert scan_declarations("\\newenvironment{acBox}{}{}\\NewDocumentEnvironment{acOther}{}{}{}") == {
        "acBox": "",
        "acOther": "",
    }


def test_colour_components_are_written_to_five_decimals():
    from texmodel.types import CMYK, RGB

    assert str(RGB(78.8 / 100, 0, 1 / 3)) == "0.788,0,0.33333"
    assert str(CMYK(0.1 + 0.2, 1, 0.000004, 0.5)) == "0.3,1,0,0.5"


def test_a_shared_base_carries_fields_and_bodies_for_its_subclasses():
    from texmodel.components import Environment

    p = Package("p", prefix="ac")

    @p.command
    class Fact(Command, unused=("text",)):
        """A fact."""

        text: Text

        def body(self):
            return r"#text"

    class _Image(Command, abstract=True):  # no docstring, and a name a control word could not have
        src: Text

        def body(self):
            return r"\includegraphics{#src}"

    class _Panel(Environment, abstract=True):
        children = [Fact.times(2, 3)]

        def begin(self):
            return r"\begin{minipage}{\linewidth}"

        def end(self):
            return r"\end{minipage}"

    @p.command
    class Photo(_Image):
        """A photo."""

    @p.command
    class Icon(_Image):
        """An icon."""

    @p.environment
    class Card(_Panel):
        """A card."""

    out = p.render()
    assert out.count("\\includegraphics{#1}") == 2 and "\\newcommand{\\acPhoto}[1]{%" in out
    assert out.count("\\begin{minipage}{\\linewidth}") == 1 and Photo("a.png").render() == "\\acPhoto{a.png}"
    assert [v.code for v in Card(Fact("a")).violations()] == ["TM-C002"]  # the base's grammar: 2 to 3 facts
    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-M043"):
        p.command(_Image)


def test_a_value_has_a_control_sequence_and_a_default_a_type_checker_can_read():
    from texmodel.components import Value, control_name
    from texmodel.types import RGB, Colour, Length

    p = Package("p", prefix="ac")

    @p.value
    class Gap(Value[Length]):
        """Gap."""

        default = Length("2mm")

    @p.value
    class Crop(Value[bool]):
        """Crop."""

        cs = "acshowcrop"
        default = True

    @p.value
    class Ink(Value[Colour]):
        """Ink."""

        default = RGB(0, 0, 0)

    assert control_name(Gap) == "acGap" and control_name(Crop) == "acshowcrop"
    assert Gap.declared_default() == Length("2mm") and Crop.declared_default() is True
    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-M042"):
        control_name(Ink)


def test_a_field_called_body_is_a_field_not_a_body():
    from texmodel.interface import arg

    p = Package("p", prefix="ac")

    class Note(Command, unused=("body",)):
        """A note."""

        text: Text
        body: Text | None = arg(default=None)

        def end(self):  # not a body either: only `body` is read for a command
            return ""

    assert Note.__tm_inline__ is None and [a.name for a in Note.__tm_args__] == ["text", "body"]
    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-M006"):
        p.command(Note)
