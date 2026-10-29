"""`texmodel.ext.colourspace`: a colour with a print build and a screen build under one name, and `colour_of`."""

import re

import pikepdf
import pytest
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.components import Value
from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.ext.colourspace import Build, ColourPair, ColourSpace, Dual, colour_of
from texmodel.ext.plates import K, Plate
from texmodel.ext.spot import Spot, SpotColour
from texmodel.interface import ColourName
from texmodel.package import Package
from texmodel.run.compiler import Compiler
from texmodel.run.testkit import check_library
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import CMYK, RGB, Colour

pkg = Package("acme-space", prefix="as")
FLAG = ColourSpace().declare(pkg)


@pkg.value
class Ink(Value[Dual]):
    """Text ink."""

    default = ColourPair(cmyk=K(0.95), rgb="2d2c2b")


@pkg.value
class Web(Value[Dual]):
    """A screen-only colour."""

    colour_name = "asWeb"
    default = ColourPair(rgb="0F8CB8")


@pkg.value
class Plain(Value[Colour]):
    """A plain colour."""

    default = CMYK(0, 0, 0, 1)


def test_the_option_the_flag_and_both_builds_of_each_colour_are_declared():
    sty = pkg.render()
    assert r"\newif\ifasCmyk" in sty and r"\asCmyktrue" in sty and r"\ProcessKeyOptions [ acme-space ]" in sty
    assert "cmyk .legacy_if_set:n = asCmyk ," in sty and "rgb .legacy_if_set_inverse:n = asCmyk ," in sty
    assert sty.index("ProcessKeyOptions") < sty.index(r"\definecolor")  # the options come before every colour
    assert FLAG.__name__ == "Cmyk" and pkg.check_parts() == []
    assert r"\ifasCmyk" in sty and r"\definecolor{as-ink}{cmyk}{0,0,0,0.95}" in sty
    assert r"\definecolor{as-ink}{HTML}{2D2C2B}" in sty and r"\definecolor{asWeb}{HTML}{0F8CB8}" in sty
    assert r"\definecolor{asWeb}{cmyk}" not in sty  # a screen-only colour has no print build


def test_the_default_build_is_chosen_by_the_declaration():
    rgb_first = Package("acme-rgb", prefix="ar")
    ColourSpace(Build.RGB).declare(rgb_first)
    assert r"\arCmykfalse" in rgb_first.render()


def test_a_pair_holds_hex_or_an_rgb_and_at_least_one_build():
    assert ColourPair(rgb="2d2c2b").rgb == "2D2C2B"
    assert ColourPair(rgb=RGB(1, 0.5, 0)).rgb == "FF8000" and ColourPair(cmyk=K(1)).rgb is None
    for bad in ("2d2c2", "12345g", "#2d2c2b", ""):
        with pytest.raises(DeclarationError) as raised:
            ColourPair(rgb=bad)
        assert raised.value.code == "TM-M064"
    with pytest.raises(DeclarationError) as raised:
        ColourPair()
    assert raised.value.code == "TM-M064"


def test_colourspace_may_come_after_the_colours_and_twice_is_one_option():
    late = Package("acme-late", prefix="al")

    @late.value
    class First(Value[Dual]):
        """Declared first."""

        default = ColourPair(cmyk=K(1))

    ColourSpace().declare(late)  # the options section comes before every colour, wherever it is declared
    assert late.render().index("ProcessKeyOptions") < late.render().index(r"\definecolor")
    assert ColourSpace().declare(pkg) is FLAG  # declared again the same way: the same option
    with pytest.raises(DeclarationError) as raised:
        ColourSpace(Build.RGB).declare(pkg)  # another default
    assert raised.value.code == "TM-M073"
    with pytest.raises(DeclarationError) as raised:
        ColourSpace().declare(Package("bare", prefix=""))
    assert raised.value.code == "TM-M065"


def test_colour_of_names_any_registered_colour_value():
    assert colour_of(Ink) == "as-ink" and colour_of(Web) == "asWeb" and colour_of(Plain) == "as-plain"
    other = Package("acme-other", prefix="ao")

    @other.value
    class Black(Value[Colour]):
        """K."""

        plates = {Plate.K}
        default = K(1)

    @other.value
    class Varnish(Value[SpotColour]):
        """Spot."""

        default = Spot("Scodix")

    assert colour_of(Black) == "ao-black" and colour_of(Varnish) == "ao-varnish"
    for bad in (int, FLAG):
        with pytest.raises(DeclarationError) as raised:
            colour_of(bad)  # type: ignore[arg-type]
        assert raised.value.code == "TM-M066"

    class Unregistered(Value[Dual]):
        """Never registered."""

        default = ColourPair(cmyk=K(1))

    with pytest.raises(DeclarationError) as raised:
        colour_of(Unregistered)
    assert raised.value.code == "TM-M066"


def test_a_dual_colour_tints_in_whichever_build_is_in_use_and_inks_its_print_plates():
    assert ColourName(Ink, tint=0.7) == "as-ink!70" and ColourName(Web, tint=1) == "asWeb!100"
    assert ColourPair(cmyk=K(0.5), rgb="777777").plates == {Plate.K} and ColourPair(rgb="0F8CB8").plates == frozenset()


def test_a_document_setting_redefines_both_builds_and_data_round_trips():
    doc = Document(settings=[Ink(ColourPair(cmyk=K(0.5), rgb="777777"))])
    tex = pkg.document(doc)
    assert r"\ifasCmyk\definecolor{as-ink}{cmyk}{0,0,0,0.5}\else\definecolor{as-ink}{HTML}{777777}\fi" in tex
    data = {"type": "Ink", "value": {"cmyk": [0, 0, 0, 0.5], "rgb": "777777"}}
    loaded = from_dict(pkg, {"settings": [data]})
    assert loaded.settings[0].value == ColourPair(cmyk=K(0.5), rgb="777777")
    assert to_dict(loaded)["settings"] == [data]
    only = from_dict(pkg, {"settings": [{"type": "Web", "value": {"rgb": "0F8CB8"}}]})
    assert only.settings[0].value == ColourPair(rgb="0F8CB8")
    for bad in ({"cmyk": [0, 0, 0, 70]}, {"rgb": "zz"}, {}, {"cmyk": [0, 0, 1]}, "2d2c2b"):
        with pytest.raises(ExceptionGroup):
            from_dict(pkg, {"settings": [{"type": "Ink", "value": bad}]})
    shape = json_schema(pkg)["$defs"]["InkSetting"]["properties"]["value"]
    assert set(shape["properties"]) == {"cmyk", "rgb"}


def test_a_pair_already_built_passes_a_python_validation():
    import pydantic

    adapter = pydantic.TypeAdapter(ColourPair)
    pair = ColourPair(cmyk=K(1))
    assert adapter.validate_python(pair) is pair


def fills(pdf):
    page = pdf.pages[0]
    page.contents_coalesce()
    content = page.Contents.read_bytes().decode("latin1")
    return re.findall(r"([\d. ]+) (k|rg)\b", content)


async def build(compiler, tmp_path, name, options):  # noqa: F811
    work = tmp_path / name
    work.mkdir()
    (work / "acme-space.sty").write_text(pkg.render())
    src = work / "doc.tex"
    body = rf"\textcolor{{{colour_of(Ink)}}}{{x}}\textcolor{{{ColourName(Ink, tint=0.5)}}}{{y}}"
    tex = pkg.document(Document(options=options)).replace(r"\begin{document}", "\\begin{document}\n" + body)
    src.write_text(tex)
    comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, roots=(work,))
    return await comp.compile(src, work / "out")


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_a_class_option_picks_the_build_and_the_same_name_reads_both(compiler, tmp_path):  # noqa: F811
    printed = await build(compiler, tmp_path, "print", [])
    assert printed.ok and printed.pdf, printed.diagnostics
    with pikepdf.open(printed.pdf) as pdf:
        assert ("0 0 0 0.95", "k") in [(a.strip(), b) for a, b in fills(pdf)]  # the CMYK build, by default
    screen = await build(compiler, tmp_path, "screen", ["rgb"])
    assert screen.ok and screen.pdf, screen.diagnostics
    with pikepdf.open(screen.pdf) as pdf:
        found = [(a.strip(), b) for a, b in fills(pdf)]
        assert any(  # 2D2C2B, the screen build (xcolor rounds the last digit)
            kind == "rg" and [float(x) for x in a.split()] == pytest.approx([0.17647, 0.17255, 0.16863], abs=2e-5)
            for a, kind in found
        )
        assert not [f for f in found if f[0] == "0 0 0 0.95"]


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_a_screen_only_colour_is_undefined_in_print_and_the_block_defines_the_flag(compiler, tmp_path):  # noqa: F811
    work = tmp_path / "web"
    work.mkdir()
    (work / "acme-space.sty").write_text(pkg.render())
    src = work / "doc.tex"
    src.write_text(pkg.document().replace(r"\begin{document}", "\\begin{document}\n\\textcolor{asWeb}{x}"))
    comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, roots=(work,))
    assert not (await comp.compile(src, work / "out")).ok  # xcolor: undefined colour in the print build
    assert await check_library(compiler, pkg) == []
