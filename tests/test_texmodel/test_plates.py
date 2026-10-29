"""`texmodel.ext.plates` and `Value.plates`: the plates a colour inks, and a colour value that may ink some."""

import pikepdf
import pytest
from test_texmodel_build.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.components import Value
from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.ext.plates import PROCESS, K, Plate, plates_of
from texmodel.interface import ColourName, constraint_of
from texmodel.package import Package
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import CMYK, RGB, Colour, Gray, Length
from texmodel_build.compiler import Compiler

pkg = Package("acme-ink", prefix="ac")


@pkg.value
class Ink(Value[Colour]):
    """Text ink: the black plate only."""

    plates = {Plate.K}
    default = K(0.95)


@pkg.value
class Duo(Value[Colour]):
    """Two plates."""

    plates = {Plate.C, Plate.M}
    default = CMYK(0.5, 0.2, 0, 0)


@pkg.value
class Accent(Value[Colour]):
    """Any process plate."""

    default = CMYK(0, 0.28, 0.04, 0)


def test_a_k_is_the_black_plate_alone_in_texs_fractions():
    assert (K(0.7).c, K(0.7).m, K(0.7).y, K(0.7).k) == (0, 0, 0, 0.7)
    assert str(K(0.7)) == "0,0,0,0.7" and repr(K(0.7)) == "K(0.7)"
    assert K(0.7) == K(0.7) and isinstance(K(0.7), CMYK)


@pytest.mark.parametrize("bad", [70, 1.01, -0.1, float("nan")])
def test_a_k_outside_zero_to_one_cannot_be_built(bad):
    with pytest.raises(DeclarationError) as raised:
        K(bad)
    assert raised.value.code == "TM-M017"


def test_nearest_rounds_to_a_step_and_refuses_a_bad_step():
    assert K.nearest(0.68) == K(0.7) and K.nearest(0.98) == K(1.0) and K.nearest(0.02) == K(0)
    assert K.nearest(0.33, step=0.1) == K(0.3)
    for step in (0, -0.1, 1.5):
        with pytest.raises(DeclarationError) as raised:
            K.nearest(0.5, step=step)
        assert raised.value.code == "TM-M046"


def test_plates_say_which_inks_a_colour_uses():
    assert plates_of(K(0.7)) == {Plate.K} and plates_of(CMYK(0, 0.28, 0.04, 0)) == {Plate.M, Plate.Y}
    assert plates_of(Gray(0.3)) == {Plate.K} and plates_of(Gray(1)) == frozenset()
    assert plates_of(RGB(0, 0, 0)) == PROCESS == set(Plate)
    assert Plate.K == "K" and {Plate.K} == {"K"}  # a plate is a string, a spot's is its name
    with pytest.raises(DeclarationError) as raised:
        plates_of("red")
    assert raised.value.code == "TM-M071"


def test_a_colour_value_constrains_its_default_its_settings_and_its_data():
    assert Ink.plates == {Plate.K} and constraint_of(Ink) == {Plate.K} and constraint_of(Duo) == {Plate.C, Plate.M}
    assert Accent.plates is None and constraint_of(Accent) == PROCESS  # undeclared: any process plate
    assert Ink(K(0.5)).value and Ink(Gray(0.5)).value and Duo(CMYK(0.1, 0.1, 0, 0)).value  # inside
    for outside in (CMYK(0.1, 0, 0, 0.5), RGB(0, 0, 0)):
        with pytest.raises(DeclarationError) as raised:
            Ink(outside)
        assert raised.value.code == "TM-M070"
    with pytest.raises(DeclarationError) as raised:
        Duo(CMYK(0.1, 0.1, 0.1, 0))
    assert raised.value.code == "TM-M070"
    data = {"type": "Ink", "value": {"c": 0, "m": 0, "y": 0, "k": 0.7}}
    assert from_dict(pkg, {"settings": [data]}).settings[0].value == CMYK(0, 0, 0, 0.7)
    assert to_dict(from_dict(pkg, {"settings": [data]}))["settings"] == [data]
    with pytest.raises(ExceptionGroup):
        from_dict(pkg, {"settings": [{"type": "Ink", "value": {"c": 0, "m": 0.1, "y": 0, "k": 0.7}}]})
    with pytest.raises(ExceptionGroup):
        from_dict(pkg, {"settings": [{"type": "Ink", "value": {"c": 0, "m": 0, "y": 0, "k": 70}}]})
    assert "InkSetting" in json_schema(pkg)["$defs"]


def test_plates_are_declared_for_a_colour_and_the_default_stays_inside_them():
    with pytest.raises(DeclarationError) as raised:

        class Wrong(Value[Colour]):
            """Off its plate."""

            plates = {Plate.K}
            default = CMYK(0.1, 0, 0, 0.5)

    assert raised.value.code == "TM-M070"
    with pytest.raises(DeclarationError) as raised:

        class NotAColour(Value[Length]):
            """A length."""

            plates = {Plate.K}
            default = Length("1mm")

    assert raised.value.code == "TM-M069"


def test_a_tint_of_a_one_plate_colour_is_xcolors_percent_and_keeps_the_plate():
    assert ColourName(Ink, tint=0.7) == "ac-ink!70" and ColourName(Duo, tint=0.5) == "ac-duo!50"
    assert r"\definecolor{ac-ink}{cmyk}{0,0,0,0.95}" in pkg.render()
    assert pkg.document(Document(settings=[Ink(K(0.5))])).count(r"\definecolor{ac-ink}{cmyk}{0,0,0,0.5}") == 1


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_a_tint_of_a_k_value_reaches_the_pdf_on_the_black_plate_alone(compiler, tmp_path):  # noqa: F811
    import re

    (tmp_path / "acme-ink.sty").write_text(pkg.render())
    src = tmp_path / "ink.tex"
    src.write_text(
        pkg.document(Document(settings=[Ink(K(0.9))])).replace(
            r"\begin{document}", "\\begin{document}\n" + rf"\textcolor{{{ColourName(Ink, tint=0.7)}}}{{x}}"
        )
    )
    comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, roots=(tmp_path,))
    result = comp.compile(src, tmp_path / "out")
    assert result.ok and result.pdf, result.diagnostics
    with pikepdf.open(result.pdf) as pdf:
        page = pdf.pages[0]
        page.contents_coalesce()
        content = page.Contents.read_bytes()  # pyright: ignore[reportAttributeAccessIssue]
    fills = re.findall(rb"([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) k\b", content)
    assert all(c == m == y == b"0" for c, m, y, _ in fills)  # every fill is on the black plate
    assert any(abs(float(k) - 0.63) < 0.001 for *_, k in fills)  # 0.9 tinted to 70%


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_xcolors_black_and_grays_are_the_black_plate_in_the_cmyk_model(compiler, tmp_path):  # noqa: F811
    import re

    src = tmp_path / "base.tex"
    src.write_text(
        "\\documentclass{article}\\usepackage[cmyk]{xcolor}\\begin{document}"
        "\\textcolor{black}{a}\\textcolor{gray}{b}\\textcolor{darkgray}{c}\\textcolor{lightgray}{d}\\end{document}"
    )
    comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, roots=(tmp_path,))
    result = comp.compile(src, tmp_path / "out")
    assert result.ok and result.pdf, result.diagnostics
    with pikepdf.open(result.pdf) as pdf:
        page = pdf.pages[0]
        page.contents_coalesce()
        content = page.Contents.read_bytes()  # pyright: ignore[reportAttributeAccessIssue]
    fills = re.findall(rb"([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) k\b", content)
    assert fills and all(c == m == y == b"0" for c, m, y, _ in fills)  # no gray fill uses another plate
