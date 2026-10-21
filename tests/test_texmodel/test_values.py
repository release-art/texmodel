"""Value[T] (M1a, M6, M7, M8, M14, G2): the type decides the declaration; refusals carry stable codes."""

import types

import pytest

from texmodel.components import Command, Value
from texmodel.errors import DeclarationError
from texmodel.package import Package
from texmodel.types import CMYK, RGB, Bool, Colour, Gray, Length


def pkg() -> Package:
    return Package("p", prefix="ac")


def refused(code: str):
    return pytest.raises(DeclarationError, check=lambda e: e.code == code)


def sty(p: Package) -> str:
    return p.render(version="0.1.0")


def test_each_type_renders_its_own_declaration():
    p = pkg()

    @p.value
    class FactGap(Value[Length]):
        """Space under each fact."""

        default = Length("2.0mm")

    @p.value
    class BrandRed(Value[Colour]):
        """Red."""

        default = RGB(0.8, 0, 0.1)

    @p.value
    class Mid(Value[Colour]):
        """Grey."""

        default = Gray(0.5)

    @p.value
    class Compact(Value[Bool]):
        """Tighten."""

        default = True

    text = sty(p)
    assert "% Space under each fact.\n% from test_texmodel.test_values." in text and "FactGap (value: Length)\n" in text
    assert "\\newlength{\\acFactGap}\n\\setlength{\\acFactGap}{2mm}\n" in text
    assert "\\definecolor{ac-brand-red}{rgb}{0.8,0,0.1}" in text and "\\definecolor{ac-mid}{gray}{0.5}" in text
    assert "\\newif\\ifacCompact\n\\acCompacttrue\n" in text
    assert p.required_packages == ("xcolor",) and text.count("\\RequirePackage{xcolor}") == 1
    assert text.index("\\ProvidesPackage") < text.index("\\RequirePackage") < text.index("\\newlength")


def test_no_colour_no_require_package(acme):
    p = pkg()

    @p.value
    class Gap(Value[Length]):
        """Gap."""

        default = Length("1pt")

    assert p.required_packages == () and "RequirePackage" not in sty(p)


def test_requirements_are_the_sorted_union_of_what_components_declare():
    p = pkg()

    @p.value
    class Ink(Value[Colour]):
        """Ink."""

        needs_packages = ("tikz", "xcolor")
        default = CMYK(0, 0, 0, 1)

    @p.value
    class Paper(Value[Colour]):
        """Paper."""

        needs_packages = ("calc",)
        default = Gray(1)

    assert Ink.needs_packages == ("tikz", "xcolor") and Paper.needs_packages == ("calc", "xcolor")
    assert p.required_packages == ("calc", "tikz", "xcolor")
    assert sty(p).count(
        "\\RequirePackage"
    ) == 3 and "\\RequirePackage{calc}\n\\RequirePackage{tikz}\n\\RequirePackage{xcolor}" in sty(p)


def test_registration_order_is_output_order_across_commands_and_values():
    p = pkg()

    @p.command
    class First(Command, body="x"):
        """First."""

    @p.value
    class Second(Value[Bool]):
        """Second."""

        default = False

    @p.command
    class Third(Command, body="x"):
        """Third."""

    text = sty(p)
    assert text.index("acFirst") < text.index("acSecond") < text.index("acThird")


def test_value_declarations_are_refused_when_the_class_is_defined():
    with refused("TM-M001"):

        class Bad2(Value[Bool]):
            """Digits."""

            default = True

    with refused("TM-M002"):

        class Undocumented(Value[Bool]):
            default = True

    for base in (Value, Value[int], Value[CMYK], Value[Length | bool]):
        with refused("TM-M012"):
            types.new_class("NotAKind", (base,), None, lambda ns: ns.update(__doc__="Doc.", default=1))

    with refused("TM-M013"):

        class NoDefault(Value[Length]):
            """No default."""

    for default in ("2mm", 2, 0):
        with refused("TM-M014"):
            types.new_class("Wrong", (Value[Length],), None, lambda ns, d=default: ns.update(__doc__="Doc.", default=d))
    with refused("TM-M014"):

        class IntForBool(Value[Bool]):
            """1 is not a bool."""

            default = 1  # pyright: ignore[reportAssignmentType]

    with refused("TM-M014"):

        class ColourForLength(Value[Length]):
            """Wrong type."""

            default = Gray(0)  # pyright: ignore[reportAssignmentType]


def test_collisions_stay_within_their_namespace():
    p = pkg()

    @p.command
    class Compact(Command, body="x"):  # pyright: ignore[reportRedeclaration]
        """Command."""

    with refused("TM-M007") as info:

        @p.value
        class Compact(Value[Bool]):  # noqa: F811  # pyright: ignore[reportRedeclaration]
            """Same control sequence."""

            default = False

    assert "\\acCompact is already declared by" in str(info.value)

    @p.value
    class Ink(Value[Colour]):  # pyright: ignore[reportRedeclaration]
        """Colour ac-ink."""

        default = Gray(0)

    @p.command
    class Ink(Command, body="x"):  # noqa: F811  # pyright: ignore[reportRedeclaration]  (colour vs control: no clash)
        """Command \\acInk."""

    with refused("TM-M007") as info:

        @p.value
        class Ink(Value[Colour]):  # noqa: F811  # pyright: ignore[reportRedeclaration]
            """Colour ac-ink twice."""

            default = Gray(1)

    assert "colour ac-ink is already declared by" in str(info.value)


def test_a_boolean_owns_its_switches():
    p = pkg()

    @p.value
    class Compact(Value[Bool]):
        """Flag."""

        default = False

    with refused("TM-M007"):

        @p.command
        class Compacttrue(Command, body="x"):  # noqa: N801
            """Collides with the switch."""

    assert "Compacttrue" not in sty(p).split("\\newif")[0]


def test_body_references_are_checked_when_output_is_asked_for_not_when_registered():
    p = pkg()

    @p.command
    class Fact(Command, body=r"\acLater \acCompacttrue"):
        """Names components declared after it."""

    with refused("TM-M015") as info:
        p.files()
    assert (
        "Fact: body uses \\acLater" in str(info.value) and "\\acLater" in str(info.value) and info.value.path == "Fact"
    )

    @p.command
    class Later(Command, body="x"):
        """Declared late."""

    with refused("TM-M015"):
        p.render()  # \acCompacttrue is still unknown

    @p.value
    class Compact(Value[Bool]):
        """Flag."""

        default = False

    assert "\\acLater" in p.files()["p.sty"]


def test_only_prefixed_capitalised_control_words_are_checked():
    p = pkg()

    @p.command
    class Quiet(Command, body="\\ac@x \\\\acNope \\acfoo \\ifacZip\\fi \\textbf \\% \\acQuiet % \\acCommented\n"):
        """Internals, unprefixed names, line breaks and comments are not ours."""

    assert "acQuiet" in p.files()["p.sty"]
