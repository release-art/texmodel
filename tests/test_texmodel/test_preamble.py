"""Typed preamble entries (§21a 10): rendered text, slot rules and plan paths."""

import pytest
from test_texmodel_build.test_compile_tex import compiler, fonts, require_files  # noqa: F401

from texmodel.components import Passthrough
from texmodel.errors import DeclarationError
from texmodel.package import Package, PreambleSlots
from texmodel.preamble import GraphicsPath, InputIfExists, InputPath, PassOption, RequireMetadata
from texmodel.std import latex
from texmodel.types import Raw


def test_entries_render_to_the_tex_a_hand_written_line_would_have():
    assert PassOption("xcolor", "table").raw() == Raw(r"\PassOptionsToPackage{table}{xcolor}")
    assert InputPath("res/", "more/").raw().tex == r"\makeatletter\def\input@path{{res/}{more/}}\makeatother"
    assert InputIfExists("deck-variant").raw().tex == r"\InputIfFileExists{deck-variant}{}{}"
    assert GraphicsPath("img/").raw().tex == r"\graphicspath{{}{img/}}"
    assert GraphicsPath("img/", include_cwd=False).raw().tex == r"\graphicspath{{img/}}"
    meta = RequireMetadata(lang="en-GB", pdfstandard="A-2b", pdftitle="A, B")
    assert meta.raw().tex == r"\DocumentMetadata{lang=en-GB, pdfstandard=A-2b, pdftitle={A, B}}"


def test_a_document_places_entries_and_names_them_by_path():
    pkg = Package("pre", prefix="pr", adopted=True)
    slots = PreambleSlots(
        before_class=(RequireMetadata(lang="en"),),
        before_package=(InputPath("res/"), Raw(r"\relax")),
        after_package=(GraphicsPath("img/"),),
    )
    plan = pkg.plan(preamble=slots)
    assert [(x.path, x.tex) for x in plan.lines if x.path.startswith("preamble")] == [
        ("preamble.before_class[0]", r"\DocumentMetadata{lang=en}"),
        ("preamble.before_package[0]", r"\makeatletter\def\input@path{{res/}}\makeatother"),
        ("preamble.before_package[1]", r"\relax"),
        ("preamble.after_package[0]", r"\graphicspath{{}{img/}}"),
    ]


def test_an_entry_in_the_wrong_slot_is_refused_with_its_path():
    pkg = Package("pre", prefix="pr", adopted=True)
    slots = PreambleSlots(
        before_class=(PassOption("a", "b"), GraphicsPath("x/")),
        before_package=(RequireMetadata(a="b"),),
        after_package=(InputPath("r/"), Raw(r"\anything")),
    )
    with pytest.raises(ExceptionGroup) as group:
        pkg.plan(preamble=slots)
    found = [(e.code, e.path) for e in group.value.exceptions]  # pyright: ignore[reportAttributeAccessIssue]
    assert found == [
        ("TM-C008", "preamble.before_class[1]"),
        ("TM-C008", "preamble.before_package[0]"),
        ("TM-C008", "preamble.after_package[0]"),
    ]


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_document_metadata_is_accepted_and_reaches_the_pdf(compiler, tmp_path):  # noqa: F811
    """`RequireMetadata` before `\\documentclass`, as the reference image's LaTeX reads it (needs `tagpdf-base`)."""
    import pikepdf

    require_files(compiler, "tagpdf-base.sty")
    slots = PreambleSlots(before_class=(RequireMetadata(lang="en-GB", pdfversion="1.7"),))
    plan = latex.package.plan(Passthrough(Raw("x")), preamble=slots)  # the kernel header: no \\usepackage line
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "d.tex").write_text(plan.text, encoding="utf-8")
    result = compiler.compile(tmp_path / "src" / "d.tex", tmp_path / "out", plan=plan)
    assert result.ok, [(d.path, d.message) for d in result.errors]
    with pikepdf.open(result.pdf) as pdf:  # pyright: ignore[reportArgumentType]
        assert pdf.pdf_version == "1.7" and str(pdf.Root.Lang) == "en-GB"


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_input_if_exists_reads_a_file_that_is_there_and_ignores_one_that_is_not(compiler, tmp_path):  # noqa: F811
    slots = PreambleSlots(after_package=(InputIfExists("variant"), InputIfExists("absent")))
    check = Passthrough(
        Raw(r"\ifdefined\variantloaded\else\errmessage{variant.tex was not read}\fi x")
    )  # "x": a page, or there is no PDF
    plan = latex.package.plan(check, preamble=slots)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "variant.tex").write_text(r"\def\variantloaded{1}", encoding="utf-8")
    (tmp_path / "src" / "d.tex").write_text(plan.text, encoding="utf-8")
    result = compiler.compile(tmp_path / "src" / "d.tex", tmp_path / "out", plan=plan)
    assert result.ok, [(d.path, d.message) for d in result.errors]


def test_input_if_exists_sits_before_or_after_the_package_and_refuses_a_bad_name():
    pkg = Package("pre", prefix="pr", adopted=True)
    slots = PreambleSlots(before_package=(InputIfExists("opts"),), after_package=(InputIfExists("variant"),))
    assert [(x.path, x.tex) for x in pkg.plan(preamble=slots).lines if x.path.startswith("preamble")] == [
        ("preamble.before_package[0]", r"\InputIfFileExists{opts}{}{}"),
        ("preamble.after_package[0]", r"\InputIfFileExists{variant}{}{}"),
    ]
    with pytest.raises(ExceptionGroup) as group:
        pkg.plan(preamble=PreambleSlots(before_class=(InputIfExists("x"),)))
    assert [e.code for e in group.value.exceptions] == ["TM-C008"]  # pyright: ignore[reportAttributeAccessIssue]
    for bad in ("", "a b", "a}b", "-a", "a\\b"):
        with pytest.raises(DeclarationError) as failed:
            InputIfExists(bad)
        assert failed.value.code == "TM-M044"
