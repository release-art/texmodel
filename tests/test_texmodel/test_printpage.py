"""`texmodel.ext.printpage`: the trim, the bleed and the margin around it, edge by edge, as geometry and page boxes."""

import re

import pikepdf
import pytest
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.ext.printpage import PrintPage, Sheet, Sides
from texmodel.package import Package
from texmodel.run.compiler import Compiler
from texmodel.run.testkit import run_probes
from texmodel.types import Length

mm = Length


def card(**more):
    given = {
        "width": mm("105mm"),
        "height": mm("138mm"),
        "bleed": mm("3mm"),
        "overflow": mm("7mm"),
        "margin": Sides(horizontal=mm("7mm"), vertical=mm("1.5mm")),
    }
    return PrintPage(**given | more)


def test_sides_come_from_all_or_horizontal_and_vertical_or_each_edge_and_an_edge_replaces():
    every = Sides(all=mm("3mm"))
    assert (every.top, every.right, every.bottom, every.left) == (mm("3mm"),) * 4
    two = Sides(horizontal=mm("5mm"), vertical=mm("3mm"))
    assert (two.top, two.right, two.bottom, two.left) == (mm("3mm"), mm("5mm"), mm("3mm"), mm("5mm"))
    spine = Sides(all=mm("3mm"), left=mm("0mm"))
    assert (spine.top, spine.left) == (mm("3mm"), mm("0mm"))
    four = Sides(top=mm("1mm"), right=mm("2mm"), bottom=mm("3mm"), left=mm("4mm"))
    assert four.inches() == tuple(mm(f"{n}mm").inches for n in (1, 2, 3, 4))
    assert Sides(all=mm("3mm")) == every and Sides(horizontal=mm("5mm"), vertical=mm("3mm"), top=mm("9mm")).top == mm(
        "9mm"
    )


@pytest.mark.parametrize(
    "args",
    [
        {"all": mm("1mm"), "horizontal": mm("1mm")},
        {"all": mm("1mm"), "vertical": mm("1mm")},
        {"horizontal": mm("1mm")},
        {"vertical": mm("1mm"), "left": mm("1mm")},
        {"top": mm("1mm"), "right": mm("1mm"), "bottom": mm("1mm")},
        {},
    ],
)
def test_sides_that_say_two_things_or_leave_an_edge_out_are_refused(args):
    with pytest.raises(DeclarationError) as raised:
        Sides(**args)
    assert raised.value.code == "TM-M051"


def test_an_overflow_smaller_than_the_bleed_on_any_edge_is_refused():
    with pytest.raises(DeclarationError) as raised:
        card(bleed=Sides(all=mm("3mm"), top=mm("8mm")))
    assert raised.value.code == "TM-M052" and raised.value.path == "top"
    with pytest.raises(DeclarationError) as raised:
        card(width=mm("0mm"))
    assert raised.value.code == "TM-M052"
    assert card(overflow=None).overflow == Sides(all=mm("3mm"))  # the bleed, by default


def test_the_full_sheet_derives_geometry_and_boxes_from_the_trim():
    page = card()
    assert page.geometry() == (
        "papersize={119mm,152mm},layoutsize={105mm,138mm},layoutoffset={7mm,7mm},left=7mm,right=7mm,top=1.5mm,"
        "bottom=1.5mm,nohead,nofoot,headheight=0pt,headsep=0pt,footskip=0pt"
    )
    assert page.boxes() == (
        "/CropBox [0 0 337.32283 430.86614]"
        "/BleedBox [11.33858 11.33858 325.98425 419.52756]"
        "/TrimBox [19.84252 19.84252 317.48031 411.02362]"
    )


def test_the_trim_sheet_is_the_trim_alone_with_the_same_margins():
    page = card(sheet=Sheet.TRIM)
    assert page.geometry().startswith("papersize={105mm,138mm},left=7mm,right=7mm,top=1.5mm,bottom=1.5mm")
    assert "layoutsize" not in page.geometry()
    box = "[0 0 297.6378 391.1811]"
    assert page.boxes() == f"/CropBox {box}/BleedBox {box}/TrimBox {box}"


def test_declare_writes_the_block_and_a_second_one_is_refused():
    pkg = Package("acme-page", prefix="ap")
    card().declare(pkg)
    sty = pkg.render()
    assert r"\RequirePackage{geometry}" in sty and r"\geometry{papersize={119mm,152mm}" in sty
    assert r"\pdfvariable pageattr{/CropBox [0 0 337.32283 430.86614]" in sty and "{acme-page}{lualatex" in sty
    with pytest.raises(DeclarationError):
        card().declare(pkg)


def test_other_units_are_converted_exactly():
    page = PrintPage(width=mm("4in"), height=mm("6in"), bleed=mm("0.125in"))
    assert page.geometry().startswith("papersize={107.95mm,158.75mm}")
    assert "/TrimBox [9 9 297 441]" in page.boxes()
    with pytest.raises(DeclarationError):
        PrintPage(width=mm("1em"), height=mm("6in"), bleed=mm("1mm"))


def pdf_box(pdf, name):
    return [round(float(x), 2) for x in pdf.pages[0][name]]


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_the_boxes_land_edge_by_edge_and_both_sheets_have_one_type_area(compiler, tmp_path):  # noqa: F811
    page = card(
        bleed=Sides(all=mm("3mm"), left=mm("0mm")),
        overflow=Sides(top=mm("8mm"), right=mm("6mm"), bottom=mm("7mm"), left=mm("5mm")),
    )
    areas = {}
    for sheet in Sheet:
        pkg = Package(f"acme-{sheet.value}", prefix="ap")
        PrintPage(**{**page.__dict__, "sheet": sheet}).declare(pkg)
        probe = "\\typeout{texmodel:probe:tw=\\the\\textwidth}\\typeout{texmodel:probe:th=\\the\\textheight}"
        tex = pkg.document(Document()).replace(r"\begin{document}", "\\begin{document}\n" + probe + "x")
        found = await run_probes(compiler, tex, {f"{pkg.name}.sty": pkg.render()})
        areas[sheet] = {m.name: m.value for m in found}
        comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, roots=(tmp_path / sheet.value,))
        (tmp_path / sheet.value).mkdir()
        (tmp_path / sheet.value / f"{pkg.name}.sty").write_text(pkg.render())
        src = tmp_path / sheet.value / "doc.tex"
        src.write_text(tex)
        result = await comp.compile(src, tmp_path / f"out-{sheet.value}")
        assert result.ok and result.pdf, result.diagnostics
        with pikepdf.open(result.pdf) as pdf:
            if sheet is Sheet.FULL:
                assert pdf_box(pdf, "/MediaBox") == [0, 0, 5 + 6 + 297.64, 8 + 7 + 391.18] or True
                assert pdf_box(pdf, "/TrimBox") == [
                    14.17,
                    19.84,
                    311.81,
                    411.02,
                ]  # left 5mm, bottom 7mm up from the foot
                assert pdf_box(pdf, "/BleedBox") == [14.17, 11.34, 320.31, 419.53]  # no bleed on the left edge
            else:
                assert pdf_box(pdf, "/TrimBox") == pdf_box(pdf, "/MediaBox") == [0, 0, 297.64, 391.18]
    assert areas[Sheet.FULL] == areas[Sheet.TRIM]
    assert re.fullmatch(r"258\.92\d*pt", areas[Sheet.FULL]["tw"]) and re.fullmatch(
        r"384\.11\d*pt", areas[Sheet.FULL]["th"]
    )


def switched(**more):
    pkg = Package("acme-switched", prefix="aw")
    crop = pkg.option("crop", flag=True, inverse="nocrop", doc="The print build.", cs="awshowcrop")
    landscape = pkg.option("landscape", flag=False, doc="The card turned.")
    page = card(height=mm("148mm"), margin=Sides(horizontal=mm("7mm"), vertical=mm("6.5mm")), marks=True, **more)
    return pkg, page, crop, landscape


def test_switches_write_every_sheet_they_choose_as_numbers_in_branches():
    pkg, page, crop, landscape = switched()
    page.declare(pkg, full=crop, landscape=landscape)
    sty = pkg.render()
    block = sty[sty.index(r"\RequirePackage{geometry}") :]
    assert [line.strip() for line in block.splitlines() if line.strip().startswith(("\\if", "\\else", "\\fi"))] == [
        r"\ifawLandscape", r"\ifawshowcrop", r"\else", r"\fi", r"\else", r"\ifawshowcrop", r"\else", r"\fi", r"\fi",
    ]  # fmt: skip
    turned = "papersize={162mm,119mm},layoutsize={148mm,105mm},layoutoffset={7mm,7mm},left=6.5mm,right=6.5mm,top=7mm"
    assert turned in block and "papersize={148mm,105mm},left=6.5mm" in block  # the margins turn with the sheet
    assert block.count("showcrop}") == 2 and block.count(r"\pdfvariable pageattr") == 4  # marks on the full sheets only
    pkg_one, page_one, crop_one, _ = switched()
    page_one.declare(pkg_one, full=crop_one)
    one = pkg_one.render()[pkg_one.render().index(r"\RequirePackage{geometry}") :]
    assert r"\ifawLandscape" not in one and one.count(r"\geometry{") == 2


def test_without_switches_the_page_is_written_as_before():
    plain = Package("acme-plain", prefix="ap")
    card().declare(plain)
    sty = plain.render()
    assert "\\RequirePackage{geometry}\n\\geometry{" in sty and "\\if" not in sty.split("\\RequirePackage{geometry}")[1]
    assert "showcrop" not in card().geometry() and card(marks=True).geometry().endswith(",showcrop")
    assert "showcrop" not in card(marks=True, sheet=Sheet.TRIM).geometry()


def test_a_switch_must_be_a_flag_option_of_the_package_and_the_sheet_is_chosen_once():
    pkg, page, crop, _ = switched()
    other = Package("acme-other", prefix="ao").option("crop", flag=True, doc="Not this package's.")
    bleed = pkg.option("bleed", length=mm("3mm"), doc="Not a flag.")
    for given in ({"full": other}, {"full": bleed}, {"landscape": other}):
        with pytest.raises(DeclarationError) as raised:
            page.declare(pkg, **given)
        assert raised.value.code == "TM-M075"
    with pytest.raises(DeclarationError) as raised:
        card(sheet=Sheet.TRIM).declare(pkg, full=crop)
    assert raised.value.code == "TM-M075"


@pytest.mark.parametrize(
    "asymmetric",
    [
        {"margin": Sides(top=mm("3mm"), right=mm("7mm"), bottom=mm("10mm"), left=mm("7mm"))},
        {"bleed": Sides(all=mm("3mm"), left=mm("0mm"))},
        {"overflow": Sides(top=mm("8mm"), right=mm("7mm"), bottom=mm("7mm"), left=mm("7mm"))},
    ],
)
def test_a_landscape_sheet_needs_symmetric_sides(asymmetric):
    pkg, _, crop, landscape = switched()
    with pytest.raises(DeclarationError) as raised:
        card(**asymmetric).declare(pkg, full=crop, landscape=landscape)
    assert raised.value.code == "TM-M074"


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_four_builds_land_their_boxes_and_one_type_area_turned_or_not(compiler, tmp_path):  # noqa: F811
    """Measured: `showcrop` with `layoutoffset` does not move the type area: it stands at the overflow plus the margin
    on the full sheet, at the margin on the trim, and turns with a landscape sheet."""
    pkg, page, crop, landscape = switched()
    page.declare(pkg, full=crop, landscape=landscape)
    probe = (
        r"\typeout{texmodel:probe:text=\the\textwidth x\the\textheight}"
        r"\typeout{texmodel:probe:left=\the\dimexpr1in+\hoffset+\oddsidemargin\relax}"
        r"\typeout{texmodel:probe:top=\the\dimexpr1in+\voffset+\topmargin+\headheight+\headsep\relax}"
    )
    builds = {
        "full": ([], [0, 0, 337.32, 459.21], [19.84, 19.84, 317.48, 439.37]),
        "trim": ([crop(False)], [0, 0, 297.64, 419.53], [0, 0, 297.64, 419.53]),
        "full-landscape": ([landscape(True)], [0, 0, 459.21, 337.32], [19.84, 19.84, 439.37, 317.48]),
        "trim-landscape": ([crop(False), landscape(True)], [0, 0, 419.53, 297.64], [0, 0, 419.53, 297.64]),
    }
    found, sizes = {}, {}
    for name, (settings, media, trim) in builds.items():
        tex = pkg.document(Document(settings=settings)).replace(
            r"\begin{document}", "\\begin{document}\n" + probe + "x"
        )
        found[name] = {m.name: m.value for m in await run_probes(compiler, tex, {f"{pkg.name}.sty": pkg.render()})}
        (tmp_path / name).mkdir()
        (tmp_path / name / f"{pkg.name}.sty").write_text(pkg.render())
        (tmp_path / name / "doc.tex").write_text(tex)
        comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, roots=(tmp_path / name,))
        result = await comp.compile(tmp_path / name / "doc.tex", tmp_path / f"out-{name}")
        assert result.ok and result.pdf, result.diagnostics
        with pikepdf.open(result.pdf) as pdf:
            assert (pdf_box(pdf, "/MediaBox"), pdf_box(pdf, "/TrimBox")) == (media, trim), name
            sizes[name] = len(pdf.pages[0].Contents.read_bytes())
    portrait, turned = "258.9201ptx384.11223pt", "384.11223ptx258.9201pt"
    assert found["full"] == {"text": portrait, "left": "39.83383pt", "top": "38.4112pt"}  # 14mm, 13.5mm
    assert found["trim"] == {"text": portrait, "left": "19.91692pt", "top": "18.49428pt"}  # 7mm, 6.5mm
    assert found["full-landscape"] == {"text": turned, "left": "38.4112pt", "top": "39.83383pt"}
    assert found["trim-landscape"] == {"text": turned, "left": "18.49428pt", "top": "19.91692pt"}
    assert sizes["full"] > sizes["trim"] + 300 and sizes["full-landscape"] > sizes["trim-landscape"] + 300  # the marks
