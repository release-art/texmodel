"""`texmodel.ext.kplate`: colours on the black plate only, bounded like every colour, and tints that stay on it."""

import re

import pikepdf
import pytest
from test_texmodel_build.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.components import Value
from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.ext.kplate import K, KOnly, Plate, is_single_plate, plates, tint
from texmodel.package import Package
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import CMYK, RGB, Colour, Gray
from texmodel_build.compiler import Compiler

pkg = Package("acme-ink", prefix="ac")


@pkg.value
class Ink(Value[KOnly]):
    """Text ink."""

    default = K(0.95)


@pkg.value
class Accent(Value[Colour]):
    """An accent on several plates."""

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


def test_a_value_of_k_holds_only_a_k_and_renders_one_plate():
    assert r"\definecolor{ac-ink}{cmyk}{0,0,0,0.95}" in pkg.render()
    with pytest.raises(DeclarationError, match="expected"):
        Ink(CMYK(0, 0, 0, 0.5))  # type: ignore[arg-type]
    with pytest.raises(DeclarationError, match="expected"):
        Ink(0.7)  # type: ignore[arg-type]
    assert r"\definecolor{ac-ink}{cmyk}{0,0,0,0.7}" in pkg.document(Document(settings=[Ink(K(0.7))]))


def test_a_k_default_that_is_not_a_k_is_refused_when_the_class_is_declared():
    with pytest.raises(DeclarationError) as raised:

        class Wrong(Value[KOnly]):
            """Not on one plate."""

            default = CMYK(0, 0, 0, 0.5)  # type: ignore[assignment]

    assert raised.value.code == "TM-M014"


def test_data_is_bounded_too_and_round_trips_as_a_fraction():
    doc = from_dict(pkg, {"settings": [{"type": "Ink", "value": 0.7}]})
    assert doc.settings[0].value == K(0.7)
    assert to_dict(doc)["settings"] == [{"type": "Ink", "value": 0.7}]
    for bad in (70, -1, "dark"):
        with pytest.raises(ExceptionGroup):
            from_dict(pkg, {"settings": [{"type": "Ink", "value": bad}]})
    schema = json_schema(pkg)["$defs"]["InkSetting"]["properties"]["value"]
    assert (schema["type"], schema["minimum"], schema["maximum"]) == ("number", 0, 1)


def test_plates_say_which_inks_a_colour_uses():
    assert plates(K(0.7)) == {Plate.K} and plates(CMYK(0, 0.28, 0.04, 0)) == {Plate.M, Plate.Y}
    assert plates(Gray(0.3)) == {Plate.K} and plates(Gray(1)) == frozenset()
    assert plates(RGB(0, 0, 0)) == set(Plate)
    assert is_single_plate(K(0.7)) and is_single_plate(Gray(0.3)) and is_single_plate(CMYK(0, 0, 0, 0))
    assert not is_single_plate(CMYK(0.1, 0, 0, 0.9)) and not is_single_plate(RGB(0, 0, 0))


def test_a_tint_of_a_k_value_is_xcolors_percent_and_other_values_are_refused():
    assert tint(Ink, 0.7) == "ac-ink!70" and tint(Ink, 0.375) == "ac-ink!37.5" and tint(Ink, 0) == "ac-ink!0"
    for other in (Accent, int):
        with pytest.raises(DeclarationError) as raised:
            tint(other, 0.5)  # type: ignore[arg-type]
        assert raised.value.code == "TM-M047"
    with pytest.raises(DeclarationError) as raised:
        tint(Ink, 70)
    assert raised.value.code == "TM-M017"


def test_a_tint_uses_the_class_colour_name():
    named = Package("acme-named", prefix="nm")

    @named.value
    class Ink(Value[KOnly]):
        """Named."""

        colour_name = "nmInk"
        default = K(1)

    assert tint(Ink, 0.5) == "nmInk!50"


def test_a_k_already_built_passes_a_python_validation_and_a_number_becomes_one():
    import pydantic

    adapter = pydantic.TypeAdapter(K)
    assert adapter.validate_python(K(0.3)) == K(0.3) and adapter.validate_python(0.3) == K(0.3)
    with pytest.raises(pydantic.ValidationError):
        adapter.validate_python(30)


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_a_tint_of_a_k_value_reaches_the_pdf_on_the_black_plate_alone(compiler, tmp_path):  # noqa: F811
    (tmp_path / "acme-ink.sty").write_text(pkg.render())
    src = tmp_path / "ink.tex"
    src.write_text(
        pkg.document(Document(settings=[Ink(K(0.9))]))
        .replace(r"\begin{document}", r"\begin{document}" + "\n" + rf"\textcolor{{{tint(Ink, 0.7)}}}{{x}}")
        .replace(r"\usepackage{acme-ink}", r"\usepackage[cmyk]{xcolor}\usepackage{acme-ink}")
    )
    comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, roots=(tmp_path,))
    result = comp.compile(src, tmp_path / "out")
    assert result.ok and result.pdf
    with pikepdf.open(result.pdf) as pdf:
        page = pdf.pages[0]
        page.contents_coalesce()
        content = page.Contents.read_bytes()  # pyright: ignore[reportAttributeAccessIssue]
    fills = re.findall(rb"([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) k\b", content)
    assert all(c == m == y == b"0" for c, m, y, _ in fills)  # every fill is on the black plate
    assert any(abs(float(k) - 0.63) < 0.001 for *_, k in fills)  # 0.9 tinted to 70%
