"""Typed preamble entries (§21): rendered text, slot rules and plan paths."""

import datetime

import pytest
from test_texmodel_run.test_compile_tex import compiler, fonts, require_files  # noqa: F401

from texmodel.components import Passthrough
from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.interface import ColourName
from texmodel.package import Package
from texmodel.preamble import (
    GraphicsPath,
    InputIfExists,
    InputPath,
    PassOption,
    PdfInfo,
    PreambleSlots,
    RequireMetadata,
    TrailerId,
)
from texmodel.std import beamer, hyperref, latex, ltx_talk
from texmodel.types import Name, Raw


def test_entries_render_to_the_tex_a_hand_written_line_would_have():
    assert PassOption("xcolor", "table").raw() == Raw(r"\PassOptionsToPackage{table}{xcolor}")
    assert InputPath("res/", "more/").raw().tex == r"\makeatletter\def\input@path{{res/}{more/}}\makeatother"
    assert InputIfExists("deck-variant").raw().tex == r"\InputIfFileExists{deck-variant}{}{}"
    assert GraphicsPath("img/").raw().tex == r"\graphicspath{{}{img/}}"
    assert GraphicsPath("img/", include_cwd=False).raw().tex == r"\graphicspath{{img/}}"
    meta = RequireMetadata(lang="en-GB", pdfstandard=("A-2b",), extra={"tagging": "on"})
    assert meta.raw().tex == r"\DocumentMetadata{lang=en-GB, pdfstandard=A-2b, tagging=on}"
    assert RequireMetadata(pdfstandard=("A-2b", "X-4"), colorprofiles={"A": "a b.icc"}).raw().tex == (
        r"\DocumentMetadata{pdfstandard={A-2b,X-4}, colorprofiles={A=a b.icc}}"
    )
    assert RequireMetadata().raw().tex == r"\DocumentMetadata{}"


def test_a_document_places_entries_and_names_them_by_path():
    pkg = Package("pre", prefix="pr", adopted=True)
    slots = PreambleSlots(
        before_class=(Raw(r"\PassOptionsToPackage{a}{b}"),),
        before_package=(InputPath("res/"), Raw(r"\relax")),
        after_package=(GraphicsPath("img/"),),
    )
    plan = pkg.plan(Document(preamble=slots, metadata=RequireMetadata(lang="en"), pdf=PdfInfo(title="T")))
    assert [(x.path, x.tex) for x in plan.lines if x.path.startswith(("preamble", "metadata", "pdf"))] == [
        ("metadata", r"\DocumentMetadata{lang=en}"),
        ("preamble.before_class[0]", r"\PassOptionsToPackage{a}{b}"),
        ("preamble.before_package[0]", r"\makeatletter\def\input@path{{res/}}\makeatother"),
        ("preamble.before_package[1]", r"\relax"),
        ("pdf", r"\csname pdfmanagement_add:nnn\endcsname{Info}{Title}{(\detokenize{T})}"),
        ("pdf", r"\AddToDocumentProperties[hyperref]{pdftitle}{\detokenize{T}}"),
        ("preamble.after_package[0]", r"\graphicspath{{}{img/}}"),
    ]


def test_a_pdf_without_metadata_gets_an_empty_one_and_a_trailer_id_alone_needs_none():
    pkg = Package("pre", prefix="pr", adopted=True)
    assert pkg.plan(Document(pdf=PdfInfo(title="T"))).lines[1].tex == r"\DocumentMetadata{}"
    assert pkg.plan(Document(pdf=PdfInfo(title="T"), metadata=RequireMetadata(lang="en"))).lines[1].tex == (
        r"\DocumentMetadata{lang=en}"
    )
    plan = pkg.plan(Document(pdf=PdfInfo(trailer_id=TrailerId("AA" * 16))))
    assert [x.path for x in plan.lines if x.path in ("metadata", "pdf")] == ["pdf"]


def test_an_entry_in_the_wrong_slot_is_refused_with_its_path():
    pkg = Package("pre", prefix="pr", adopted=True)
    slots = PreambleSlots(
        before_class=(PassOption("a", "b"), GraphicsPath("x/")),
        before_package=(GraphicsPath("y/"),),
        after_package=(InputPath("r/"), Raw(r"\anything")),
    )
    with pytest.raises(ExceptionGroup) as group:
        pkg.plan(Document(preamble=slots))
    found = [(e.code, e.path) for e in group.value.exceptions]  # pyright: ignore[reportAttributeAccessIssue]
    assert found == [
        ("TM-C008", "preamble.before_class[1]"),
        ("TM-C008", "preamble.before_package[0]"),
        ("TM-C008", "preamble.after_package[0]"),
    ]


@pytest.mark.parametrize(
    ("make", "code"),
    [
        (lambda: RequireMetadata(extra={"bad key": "x"}), "TM-M091"),
        (lambda: RequireMetadata(extra={"lang": "x"}), "TM-M092"),
        (lambda: RequireMetadata(lang="a{b"), "TM-M093"),
        (lambda: RequireMetadata(colorprofiles={"A": "50%.icc"}), "TM-M093"),
        (lambda: PdfInfo(created=datetime.datetime(2026, 1, 1)), "TM-M094"),
        (lambda: PdfInfo(extra={"CreationDate": "x"}), "TM-M090"),
    ],
)
def test_the_metadata_entries_refuse_what_tex_would_misread(make, code):
    with pytest.raises(DeclarationError) as failed:
        make()
    assert failed.value.code == code


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_document_metadata_is_accepted_and_reaches_the_pdf(compiler, tmp_path):  # noqa: F811
    """`RequireMetadata` before `\\documentclass`, as the reference image's LaTeX reads it (needs `tagpdf-base`)."""
    import pikepdf

    await require_files(compiler, "tagpdf-base.sty")
    plan = latex.package.plan(
        Document(Passthrough(Raw("x")), metadata=RequireMetadata(lang="en-GB", pdfversion="1.7"))
    )  # the kernel header: no \\usepackage line
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "d.tex").write_text(plan.text, encoding="utf-8")
    result = await compiler.compile(tmp_path / "src" / "d.tex", tmp_path / "out", plan=plan)
    assert result.ok, [(d.path, d.message) for d in result.errors]
    with pikepdf.open(result.pdf) as pdf:  # pyright: ignore[reportArgumentType]
        assert pdf.pdf_version == "1.7" and str(pdf.Root.Lang) == "en-GB"


@pytest.mark.tex
@pytest.mark.timeout(300)
@pytest.mark.parametrize("package", [latex, hyperref], ids=["kernel", "hyperref"])
async def test_pdf_info_reaches_the_info_dictionary_the_xmp_and_the_trailer(compiler, tmp_path, package):  # noqa: F811
    """One declaration, three routes, the same whether or not hyperref is loaded."""
    import pikepdf

    await require_files(compiler, "tagpdf-base.sty", "hyperref.sty")
    title = "Rex & co: 50% <b> (the fox) #1 é 日本"
    info = PdfInfo(
        title=title,
        author="A. Author",
        keywords=("fox", "quick"),
        producer="Acme Press",
        creator="Acme Maker",
        created=datetime.datetime(2020, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
        modified=datetime.datetime(2021, 2, 3, 6, 5, 6, tzinfo=datetime.timezone(datetime.timedelta(hours=2))),
        trailer_id=TrailerId("00112233445566778899AABBCCDDEEFF"),
        extra={"Trapped": "False"},
    )
    plan = package.package.plan(Document(Passthrough(Raw("x")), metadata=RequireMetadata(lang="en-GB"), pdf=info))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "d.tex").write_text(plan.text, encoding="utf-8")
    result = await compiler.compile(tmp_path / "src" / "d.tex", tmp_path / "out", plan=plan)
    assert result.ok, [(d.path, d.message) for d in result.errors]
    with pikepdf.open(result.pdf) as pdf:  # pyright: ignore[reportArgumentType]
        got = {k: str(pdf.docinfo[k]) for k in ("/Title", "/Author", "/Keywords", "/Producer", "/Creator", "/Trapped")}
        assert got == {
            "/Title": title,
            "/Author": "A. Author",
            "/Keywords": "fox, quick",
            "/Producer": "Acme Press",
            "/Creator": "Acme Maker",
            "/Trapped": "False",
        }
        xmp = pdf.open_metadata()
        assert (xmp["pdf:Producer"], xmp["xmp:CreatorTool"], xmp["dc:title"]) == ("Acme Press", "Acme Maker", title)
        assert (str(pdf.docinfo.CreationDate), str(pdf.docinfo.ModDate)) == ("D:20200102030405Z", "D:20210203040506Z")
        assert (xmp["xmp:CreateDate"], xmp["xmp:ModifyDate"]) == ("2020-01-02T03:04:05Z", "2021-02-03T04:05:06Z")
        assert [bytes(i).hex().upper() for i in pdf.trailer.ID] == ["00112233445566778899AABBCCDDEEFF"] * 2


def test_a_class_that_refuses_document_metadata_stops_the_plan_and_one_that_needs_it_gets_it():
    for document, path in (
        (Document(metadata=RequireMetadata(lang="en")), "metadata"),
        (Document(pdf=PdfInfo(title="T")), "pdf"),
    ):
        with pytest.raises(ExceptionGroup) as group:
            beamer.package.plan(document)
        assert [(e.code, e.path) for e in group.value.exceptions] == [("TM-C050", path)]  # pyright: ignore[reportAttributeAccessIssue]
    beamer.package.plan(Document(pdf=PdfInfo(trailer_id=TrailerId("AA" * 16))))  # a trailer ID needs no metadata
    assert [x.tex for x in ltx_talk.package.plan(Document()).lines if x.path == "metadata"] == [r"\DocumentMetadata{}"]
    plan = ltx_talk.package.plan(Document(metadata=RequireMetadata(lang="en"), options=["aspect-ratio=4:3"]))
    assert [x.tex for x in plan.lines if x.path in ("metadata", "document")][:2] == [
        r"\DocumentMetadata{lang=en}",
        r"\documentclass[frame-title-arg=true,aspect-ratio=4:3]{ltx-talk}",
    ]


def test_class_options_of_a_package_come_before_the_documents_and_are_checked():
    pkg = Package("pre", prefix="pr", adopted=True, class_options=("a=1",))
    assert pkg.plan(Document(options=["b"])).lines[1].tex == r"\documentclass[a=1,b]{article}"
    assert pkg.plan(Document()).lines[1].tex == r"\documentclass[a=1]{article}"
    with pytest.raises(DeclarationError) as failed:
        Package("pre", prefix="pr", class_options=("a b",))
    assert failed.value.code == "TM-P014"


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_a_talk_takes_document_metadata_class_options_titles_and_styling(compiler, tmp_path):  # noqa: F811
    import pikepdf

    await require_files(compiler, "tagpdf-base.sty", "ltx-talk.cls", "NewCMSans10-Regular.otf")
    t = ltx_talk
    document = Document(
        t.EditInstance(template=t.Template.HEADER, instance=Name("std"), keys=t.HeaderKeys(color=ColourName("white"))),
        t.Frame(Passthrough(Raw("x")), title="Title", options=t.FrameOptions(vertical_alignment=t.Alignment.TOP)),
        t.Frame(Passthrough(Raw("untitled"))),
        options=t.TalkOptions(aspect_ratio=t.AspectRatio(4, 3)).options(),
        metadata=RequireMetadata(lang="en-GB"),
        pdf=PdfInfo(title="A talk"),
    )
    plan = t.package.plan(document)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "d.tex").write_text(plan.text, encoding="utf-8")
    result = await compiler.compile(tmp_path / "src" / "d.tex", tmp_path / "out", plan=plan)
    assert result.ok, [(d.path, d.message) for d in result.errors]
    with pikepdf.open(result.pdf) as pdf:  # pyright: ignore[reportArgumentType]
        width, height = (float(x) for x in pdf.pages[0].MediaBox[2:])
        assert str(pdf.docinfo["/Title"]) == "A talk" and abs(width / height - 4 / 3) < 0.01


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_input_if_exists_reads_a_file_that_is_there_and_ignores_one_that_is_not(compiler, tmp_path):  # noqa: F811
    slots = PreambleSlots(after_package=(InputIfExists("variant"), InputIfExists("absent")))
    check = Passthrough(
        Raw(r"\ifdefined\variantloaded\else\errmessage{variant.tex was not read}\fi x")
    )  # "x": a page, or there is no PDF
    plan = latex.package.plan(Document(check, preamble=slots))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "variant.tex").write_text(r"\def\variantloaded{1}", encoding="utf-8")
    (tmp_path / "src" / "d.tex").write_text(plan.text, encoding="utf-8")
    result = await compiler.compile(tmp_path / "src" / "d.tex", tmp_path / "out", plan=plan)
    assert result.ok, [(d.path, d.message) for d in result.errors]


def test_input_if_exists_sits_before_or_after_the_package_and_refuses_a_bad_name():
    pkg = Package("pre", prefix="pr", adopted=True)
    slots = PreambleSlots(before_package=(InputIfExists("opts"),), after_package=(InputIfExists("variant"),))
    assert [(x.path, x.tex) for x in pkg.plan(Document(preamble=slots)).lines if x.path.startswith("preamble")] == [
        ("preamble.before_package[0]", r"\InputIfFileExists{opts}{}{}"),
        ("preamble.after_package[0]", r"\InputIfFileExists{variant}{}{}"),
    ]
    with pytest.raises(ExceptionGroup) as group:
        pkg.plan(Document(preamble=PreambleSlots(before_class=(InputIfExists("x"),))))
    assert [e.code for e in group.value.exceptions] == ["TM-C008"]  # pyright: ignore[reportAttributeAccessIssue]
    for bad in ("", "a b", "a}b", "-a", "a\\b"):
        with pytest.raises(DeclarationError) as failed:
            InputIfExists(bad)
        assert failed.value.code == "TM-M044"
