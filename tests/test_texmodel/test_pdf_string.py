"""`PdfString` and `Value[Raw]` (§21): small types."""

import pathlib
import re

import pytest
from hypothesis import (
    given,
    strategies as st,
)
from test_texmodel_build.test_compile_tex import compiler, fonts, require_files  # noqa: F401

from texmodel.components import Command, Value
from texmodel.document import Document
from texmodel.package import Package
from texmodel.preamble import PreambleSlots, RequireMetadata
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import PDF, PdfString, Raw, Text, pdf_escape

from .test_document import refused


def test_the_marker_names_itself():
    assert repr(PDF) == "PdfString"


def test_pdf_escape_octal_escapes_what_ends_a_string_or_is_tex_markup():
    assert pdf_escape("Fox (Vulpes) 50% a\\b") == "Fox \\050Vulpes\\051 50\\045 a\\134b"
    assert pdf_escape("{#&$_^~}") == "\\173\\043\\046\\044\\137\\136\\176\\175"
    assert pdf_escape("a\nb\tc") == "a\\012b\\011c"
    assert pdf_escape("a  b   c") == "a \\040b \\040\\040c"  # a run of spaces survives TeX
    assert pdf_escape("é") == "\\376\\377\\000\\351"  # non-ASCII: UTF-16BE with a byte order mark
    assert pdf_escape("🦊") == "\\376\\377\\330\\076\\335\\212"  # a surrogate pair
    with pytest.raises(UnicodeEncodeError):
        pdf_escape("\ud800é")


def read_literal(body: str) -> str:
    """What a PDF reader makes of the body of a literal string (ISO 32000 7.3.4.2, 7.9.2.2), for the cases we write."""
    raw = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), body).encode("latin-1")
    return raw[2:].decode("utf-16-be") if raw.startswith(b"\xfe\xff") else raw.decode("ascii")


@given(st.text())
def test_a_pdf_escaped_string_reads_back_as_the_text_and_has_nothing_that_ends_it_or_starts_tex_markup(text):
    out = pdf_escape(text)
    assert not set(out) & set("(){}%#&$_^~") and out.isascii() and "\n" not in out
    assert all(part[:3].isdigit() for part in out.split("\\")[1:])  # a backslash only starts an octal escape
    assert read_literal(out) == text


def pdf_package():
    pkg = Package("pdf-demo", prefix="pd")

    @pkg.command
    class Meta(Command):
        """Writes a PDF string to the log."""

        body = r"\typeout{texmodel:probe:s=#text}.% #note"
        text: PdfString
        note: PdfString | None = None

    return pkg, Meta


def test_a_pdf_string_field_is_escaped_in_detokenize():
    _, meta = pdf_package()
    assert meta(text="A (b)").render() == r"\pdMeta{\detokenize{A \050b\051}}"
    assert meta(text="x", note="y]").render() == r"\pdMeta[{\detokenize{y]}}]{\detokenize{x}}"
    assert [v.code for v in meta(text=1).violations()] == ["TM-C003"]  # type: ignore[arg-type]
    assert "PdfString" in meta(text=1).violations()[0].message  # type: ignore[arg-type]


def test_a_pdf_string_round_trips_through_data_and_the_schema():
    _, meta = pdf_package()
    node = meta(text="A (b)")
    assert from_dict(meta, to_dict(node)) == node
    assert json_schema(meta)["properties"]["text"]["type"] == "string"


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_a_pdf_string_reaches_the_log_exactly_as_escaped(compiler, tmp_path: pathlib.Path):  # noqa: F811
    pkg, meta = pdf_package()
    text = "Fox (Vulpes) 50% {x} #1 _a_ ~b ^c $5 a\\b  two   spaces — ünï"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "pdf-demo.sty").write_text(pkg.render(), encoding="utf-8")
    (tmp_path / "src" / "d.tex").write_text(pkg.document(meta(text=text)), encoding="utf-8")
    result = compiler.compile(tmp_path / "src" / "d.tex", tmp_path / "out")
    assert result.ok, [(x.message, x.code) for x in result.diagnostics]
    assert result.probe("s") == pdf_escape(text)


# --- Value[Raw] -----------------------------------------------------------------------------------------------


def raw_package():
    pkg = Package("raw-demo", prefix="rd")

    @pkg.value
    class Footer(Value[Raw]):
        """The footer, as TeX."""

        default = Raw(r"\textit{draft}")

    return pkg, Footer


def test_a_raw_value_is_defined_and_renewed_as_tex():
    pkg, footer = raw_package()
    assert r"\newcommand{\rdFooter}{\textit{draft}}" in pkg.render() and "(value: Raw)" in pkg.render()
    text = pkg.document(Document(settings=[footer(Raw(r"\textbf{final}"))]))
    assert text.index(r"\renewcommand{\rdFooter}{\textbf{final}}") < text.index(r"\begin{document}")


def test_a_raw_value_is_checked_and_may_be_adopted_without_a_default():
    _, footer = raw_package()
    with refused("TM-M014"):
        footer("not raw")  # type: ignore[arg-type]
    adopted = Package("raw-demo", prefix="rd", adopted=True)

    @adopted.value
    class Bare(Value[Raw]):
        """No default: the hand-written package has it."""

    assert adopted.check_interface(r"\newcommand{\rdBare}{x}") == []
    with refused("TM-M013"):
        Package("raw-demo", prefix="rd").value(Bare)


def test_only_the_known_value_types_are_accepted():
    with refused("TM-M012"):

        class Bad(Value[bytes]):  # type: ignore[type-var]
            """x"""


# --- the PDF itself ---------------------------------------------------------------------------------------------

CORPUS = [
    "Fox (Vulpes)",
    ")(",
    "(",
    ")",
    "a\\b",
    "ends with backslash\\",
    "\\)",
    "50% of $5 & #1 ## _a_ ~b ^c",
    "{x} }{ {",
    "  two   spaces  ",
    "tab\there\nnew line\r\nwindows",
    "brackets [x] ] and quotes \"'`",
    "ünï — “x” ‘y’ €",
    "狐 and 🦊",
    "<hex> <<dict>> /Name",
    "",
]

TITLE_ROUTES = {
    "pdfextension": r"\pdfextension info{/#key\space(#text)}",
    "pdfmanagement": r"\csname pdfmanagement_add:nnn\endcsname{Info}{#key}{(#text)}",  # needs \DocumentMetadata
}


def info_package(route: str):
    pkg = Package("info-demo", prefix="in")

    @pkg.command
    class Put(Command):
        """Writes a custom key of the Info dictionary."""

        body = route + r"\null"  # something to typeset, so there is a page
        key: Text
        text: PdfString

    return pkg, Put


@pytest.mark.tex
@pytest.mark.timeout(300)
@pytest.mark.parametrize("route", TITLE_ROUTES)
def test_the_info_dictionary_holds_exactly_the_text(compiler, tmp_path: pathlib.Path, route):  # noqa: F811
    import pikepdf

    if route == "pdfmanagement":
        require_files(compiler, "tagpdf-base.sty")
    pkg, put = info_package(TITLE_ROUTES[route])
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "info-demo.sty").write_text(pkg.render(), encoding="utf-8")
    nodes = [put(key=f"K{i}", text=text) for i, text in enumerate(CORPUS)]
    managed = PreambleSlots(before_class=(RequireMetadata(),)) if route == "pdfmanagement" else None
    (tmp_path / "src" / "d.tex").write_text(pkg.document(Document(*nodes, preamble=managed)), encoding="utf-8")
    result = compiler.compile(tmp_path / "src" / "d.tex", tmp_path / "out")
    assert result.ok, [(x.message, x.code) for x in result.diagnostics]
    with pikepdf.open(result.pdf) as pdf:  # pyright: ignore[reportArgumentType]
        got = {i: str(pdf.docinfo[f"/K{i}"]) for i in range(len(CORPUS)) if f"/K{i}" in pdf.docinfo}
    assert got == dict(enumerate(CORPUS))


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_the_same_text_unescaped_breaks_the_dictionary(compiler, tmp_path: pathlib.Path):  # noqa: F811
    """The control: through a `Raw` field the parenthesis ends the string early, so the check above can fail."""
    import pikepdf

    pkg = Package("naive-demo", prefix="nv")

    @pkg.command
    class Put(Command):
        """Writes a custom key of the Info dictionary without escaping."""

        body = r"\pdfextension info{/#key\space(#text)}\null"
        key: Text
        text: Raw

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "naive-demo.sty").write_text(pkg.render(), encoding="utf-8")
    (tmp_path / "src" / "d.tex").write_text(pkg.document(Put(key="K0", text=Raw("a) /K1 (b"))), encoding="utf-8")
    result = compiler.compile(tmp_path / "src" / "d.tex", tmp_path / "out")
    with pikepdf.open(result.pdf) as pdf:  # pyright: ignore[reportArgumentType]
        assert "/K1" in pdf.docinfo  # the text became a key of its own
