"""`texmodel.ext.spot`: a named plate with a CMYK proxy, declared as a value, tinted, and read back from the PDF."""

import pikepdf
import pytest
from test_texmodel_build.test_compile_tex import compiler, fonts, require_files  # noqa: F401

from texmodel.components import Value
from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.ext.kplate import K, KOnly
from texmodel.ext.spot import Spot, SpotColour, tint
from texmodel.package import Package
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import CMYK
from texmodel_build.compiler import Compiler

pkg = Package("acme-spot", prefix="ap")


@pkg.value
class Varnish(Value[SpotColour]):
    """Spot-UV varnish."""

    default = Spot("Scodix", proxy=K(1))


@pkg.value
class Pantone(Value[SpotColour]):
    """A Pantone."""

    default = Spot("PANTONE 302 C", proxy=CMYK(1, 0.5, 0, 0.2))


@pkg.value
class Ink(Value[KOnly]):
    """Text ink."""

    default = K(0.95)


def test_a_spot_value_declares_the_separation_with_its_proxy():
    sty = pkg.render()
    assert r"\RequirePackage{colorspace}" in sty
    assert r"\definespotcolor{ap-varnish}{Scodix}{0,0,0,1}" in sty
    assert r"\definespotcolor{ap-pantone}{PANTONE 302 C}{1,0.5,0,0.2}" in sty


@pytest.mark.parametrize("plate", ["Scodix", "PANTONE 302 C", "Café Ünï", "PANTONE+ 1-1", "A_B", "A&B", "A~B", "A,B"])
def test_a_plate_name_with_spaces_or_punctuation_a_pdf_name_keeps_is_accepted(plate):
    assert Spot(plate).plate == plate and Spot(plate).proxy == K(1)


@pytest.mark.parametrize(
    "plate", ["", "  ", "a/b", "a(b)", "a<b", "a>b", "a[b", "a]b", "a{b}", "a%b", "a#b", "a\\b", "a\x07"]
)
def test_a_plate_name_that_would_split_a_pdf_name_or_confuse_tex_is_refused(plate):
    with pytest.raises(DeclarationError) as raised:
        Spot(plate)
    assert raised.value.code == "TM-M053"


def test_a_spot_holds_a_process_colour_proxy_in_bounds():
    with pytest.raises(DeclarationError) as raised:
        Spot("Scodix", proxy=CMYK(0, 0, 0, 70))
    assert raised.value.code == "TM-M017"


def test_a_spot_value_holds_only_a_spot():
    with pytest.raises(DeclarationError, match="expected"):
        Varnish(K(1))  # type: ignore[arg-type]
    with pytest.raises(DeclarationError) as raised:

        class Wrong(Value[SpotColour]):
            """Not a spot."""

            default = "Scodix"  # type: ignore[assignment]

    assert raised.value.code == "TM-M014"


def test_a_spot_is_declared_once_and_is_not_a_document_setting():
    """colorspace stops on a plate defined twice (`Duplicated spot name`), so a setting would only break the compile."""
    with pytest.raises(DeclarationError) as raised:
        pkg.document(Document(settings=[Varnish(Spot("Scodix", proxy=K(0.5)))]))
    assert raised.value.code == "TM-M055"


def test_data_round_trips_and_is_checked():
    data = {"type": "Pantone", "value": {"plate": "PANTONE 302 C", "proxy": [1, 0.5, 0, 0.2]}}
    doc = from_dict(pkg, {"settings": [data]})
    assert doc.settings[0].value == Spot("PANTONE 302 C", proxy=CMYK(1, 0.5, 0, 0.2))
    assert to_dict(doc)["settings"] == [data]
    for bad in (
        {"plate": "a/b", "proxy": [0, 0, 0, 1]},
        {"plate": "ok", "proxy": [0, 0, 0, 70]},
        {"plate": "ok", "proxy": [0, 0, 1]},
        {"plate": "", "proxy": [0, 0, 0, 1]},
        "Scodix",
    ):
        with pytest.raises(ExceptionGroup):
            from_dict(pkg, {"settings": [{"type": "Pantone", "value": bad}]})
    shape = json_schema(pkg)["$defs"]["PantoneSetting"]["properties"]["value"]
    assert set(shape["properties"]) == {"plate", "proxy"}


def test_a_tint_is_xcolors_percent_of_a_spot_value_only():
    assert (
        tint(Varnish, 0.6) == "ap-varnish!60"
        and tint(Pantone, 1) == "ap-pantone!100"
        and tint(Varnish, 0) == "ap-varnish!0"
    )
    for other in (Ink, int):
        with pytest.raises(DeclarationError) as raised:
            tint(other, 0.5)  # type: ignore[arg-type]
        assert raised.value.code == "TM-M054"
    with pytest.raises(DeclarationError) as raised:
        tint(Varnish, 60)
    assert raised.value.code == "TM-M017"


def test_a_tint_uses_the_class_colour_name():
    named = Package("acme-named", prefix="nm")

    @named.value
    class Foil(Value[SpotColour]):
        """A foil."""

        colour_name = "nmFoil"
        default = Spot("Foil")

    assert tint(Foil, 0.5) == "nmFoil!50"


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_the_separations_and_their_tints_reach_the_pdf(compiler, tmp_path):  # noqa: F811
    require_files(compiler, "colorspace.sty")
    (tmp_path / "acme-spot.sty").write_text(pkg.render())
    body = rf"\textcolor{{{tint(Pantone, 0.6)}}}{{x}}\textcolor{{{tint(Varnish, 1)}}}{{y}}\textcolor{{ap-varnish}}{{z}}"
    src = tmp_path / "doc.tex"
    src.write_text(pkg.document().replace(r"\begin{document}", "\\begin{document}\n" + body))
    comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, roots=(tmp_path,))
    result = comp.compile(src, tmp_path / "out")
    assert result.ok and result.pdf, result.diagnostics
    with pikepdf.open(result.pdf) as pdf:
        assert pdf.check_pdf_syntax() == []
        spaces = {
            str(v[1]): [float(x) for x in v[3].C1]
            for v in pdf.pages[0].Resources.ColorSpace.values()
            if isinstance(v, pikepdf.Array) and v[0] == "/Separation"
        }
        assert spaces == {"/PANTONE 302 C": [1, 0.5, 0, 0.2], "/Scodix": [0, 0, 0, 1]}
        page = pdf.pages[0]
        page.contents_coalesce()
        content = page.Contents.read_bytes()  # pyright: ignore[reportAttributeAccessIssue]
    assert b"0.6 sc" in content and content.count(b"1 sc") >= 2


def test_a_spot_already_built_passes_a_python_validation():
    import pydantic

    adapter = pydantic.TypeAdapter(Spot)
    spot = Spot("Scodix")
    assert adapter.validate_python(spot) is spot
    assert adapter.validate_python({"plate": "Scodix", "proxy": [0, 0, 0, 1]}) == spot
