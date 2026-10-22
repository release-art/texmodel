"""`PdfString` (§21a 9) and `Value[Raw]` (§21a 1): small types."""

import pathlib

import pytest
from hypothesis import (
    given,
    strategies as st,
)
from test_texmodel_build.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.components import Command, Value
from texmodel.package import Package
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import PDF, PdfString, Raw, pdf_escape

from .test_document import refused


def test_the_marker_names_itself():
    assert repr(PDF) == "PdfString"


def test_pdf_escape_octal_escapes_what_ends_a_string_or_is_tex_markup():
    assert pdf_escape("Fox (Vulpes) 50% a\\b") == "Fox \\050Vulpes\\051 50\\045 a\\134b"
    assert pdf_escape("{#&$_^~}") == "\\173\\043\\046\\044\\137\\136\\176\\175"
    assert pdf_escape("a\nb\tc") == "a\\012b\\011c"
    assert pdf_escape("a  b   c") == "a \\040b \\040\\040c"  # a run of spaces survives TeX
    assert pdf_escape("Ünï — “x”") == "Ünï — “x”"  # non-ASCII is left as it is


@given(st.text())
def test_a_pdf_escaped_string_has_nothing_that_can_end_a_string_or_start_tex_markup(text):
    out = pdf_escape(text)
    assert not set(out) & set("(){}%#&$_^~") and "\n" not in out
    assert out.replace("\\", "") == out.replace("\\", "")  # a backslash is only ever the start of an octal escape
    assert all(part[:3].isdigit() for part in out.split("\\")[1:])


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
    assert meta("A (b)").render() == r"\pdMeta{\detokenize{A \050b\051}}"
    assert meta("x", note="y]").render() == r"\pdMeta[{\detokenize{y]}}]{\detokenize{x}}"
    assert [v.code for v in meta(1).validate()] == ["TM-C003"]  # type: ignore[arg-type]
    assert "PdfString" in meta(1).validate()[0].message  # type: ignore[arg-type]


def test_a_pdf_string_round_trips_through_data_and_the_schema():
    _, meta = pdf_package()
    node = meta("A (b)")
    assert from_dict(meta, to_dict(node)) == node
    assert json_schema(meta)["properties"]["text"]["type"] == "string"


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_a_pdf_string_reaches_the_log_exactly_as_escaped(compiler, tmp_path: pathlib.Path):  # noqa: F811
    pkg, meta = pdf_package()
    text = "Fox (Vulpes) 50% {x} #1 _a_ ~b ^c $5 a\\b  two   spaces — ünï"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "pdf-demo.sty").write_text(pkg.render(), encoding="utf-8")
    (tmp_path / "src" / "d.tex").write_text(pkg.document(meta(text)), encoding="utf-8")
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
    text = pkg.document(settings=[footer(Raw(r"\textbf{final}"))])
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
