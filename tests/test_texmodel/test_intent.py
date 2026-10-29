"""`texmodel.ext.intent`: the output intent a document claims, and its registration, are one declaration."""

import subprocess
from typing import Any

import pikepdf
import pytest
from test_texmodel_run.test_compile_tex import compiler, fonts, require_files  # noqa: F401

from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.ext.intent import OutputCondition, OutputIntent, Standard
from texmodel.package import Package
from texmodel.run.compiler import Compiler

CONDITION = OutputCondition(
    "Acme_coated.icc", identifier="ACME 39", info="Coated acme (ISO 12647-2:2004)", registry="http://www.color.org"
)
INTENT = OutputIntent(CONDITION, standards=(Standard.X4, Standard.A2B), language="en-GB", pdf_version="1.7")


def test_the_keys_are_one_metadata_with_a_subtype_pair_for_each_standard():
    assert INTENT.keys("res/icc") == {
        "lang": "en-GB",
        "pdfstandard": "X-4,A-2b",
        "pdfversion": "1.7",
        "colorprofiles": "X=res/icc/Acme_coated.icc,A=res/icc/Acme_coated.icc",
    }
    assert OutputIntent(CONDITION, standards=(Standard.A2B,), pdf_version="1.4").keys() == {
        "pdfstandard": "A-2b",
        "pdfversion": "1.4",
        "colorprofiles": "A=Acme_coated.icc",
    }
    assert OutputIntent(CONDITION).keys() == {}


def test_the_slots_put_the_metadata_before_the_class():
    pkg = Package("acme-intent", prefix="ai")
    tex = pkg.document(Document(preamble=INTENT.slots("res/icc")))
    assert tex.index(r"\DocumentMetadata{lang=en-GB, pdfstandard={X-4,A-2b}") < tex.index(r"\documentclass")
    assert "colorprofiles={X=res/icc/Acme_coated.icc,A=res/icc/Acme_coated.icc}" in tex


def test_declare_registers_the_condition_under_both_spellings():
    pkg = Package("acme-intent", prefix="ai")
    INTENT.declare(pkg, "res/icc")
    sty = pkg.render()
    assert r"\clist_map_inline:nn { Acme_coated.icc,res/icc/Acme_coated.icc }" in sty
    assert "OutputConditionIdentifier = ACME~39" in sty and "N                         = 4" in sty
    assert r"\ExplSyntaxOn" in sty
    bare = Package("acme-bare", prefix="ab")
    INTENT.declare(bare)
    assert r"{ Acme_coated.icc }" in bare.render()


@pytest.mark.parametrize(
    ("field", "value"),
    [("profile", "a b.icc"), ("profile", "a,b.icc"), ("identifier", "a=b"), ("info", ""), ("registry", "50%")],
)
def test_a_condition_value_the_kernel_would_misread_is_refused(field, value):
    data: dict[str, Any] = {"profile": "a.icc", "identifier": "x", "info": "y", "registry": "z"} | {field: value}
    with pytest.raises(DeclarationError) as raised:
        OutputCondition(**data)
    assert raised.value.code == "TM-M048"


def test_colorants_are_one_three_or_four_and_the_metadata_values_are_safe():
    with pytest.raises(DeclarationError) as raised:
        OutputCondition("a.icc", identifier="x", info="y", colorants=2)
    assert raised.value.code == "TM-M049"
    with pytest.raises(DeclarationError, match="language"):
        OutputIntent(CONDITION, language="en,GB")


@pytest.mark.parametrize("version", [None, "2.0", "1.10", "seven"])
def test_pdf_a_2b_needs_a_pdf_version_it_allows(version):
    with pytest.raises(DeclarationError) as raised:
        OutputIntent(CONDITION, standards=(Standard.A2B,), pdf_version=version)
    assert raised.value.code == "TM-M050"
    OutputIntent(CONDITION, standards=(Standard.X4,))  # X-4 names no newest version


def icc(space: bytes, size: int = 200) -> bytes:
    return bytes(bytearray(16) + space + bytearray(16) + b"acsp" + bytearray(size - 40))


def test_a_profile_is_checked_by_its_header():
    assert CONDITION.check_profile((icc(b"CMYK"))) == []
    (wrong,) = CONDITION.check_profile((icc(b"RGB ")))
    assert wrong.code == "TM-C015" and "'RGB '" in wrong.message
    (short,) = CONDITION.check_profile(b"version https://git-lfs.github.com/spec/v1\n")
    assert short.code == "TM-C014"
    (unsigned,) = CONDITION.check_profile(bytes(bytearray(200)))
    assert unsigned.code == "TM-C014"
    gray = OutputCondition("g.icc", identifier="x", info="y", colorants=1)
    assert gray.check_profile((icc(b"GRAY"))) == []


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_the_registered_condition_reaches_the_pdf_as_an_output_intent(compiler, tmp_path):  # noqa: F811
    """A profile under a name l3pdfmeta does not know: without `declare` there is no intent; with it, both."""
    await require_files(compiler, "tagpdf-base.sty")  # PDF/A loads it; the base image has not got it yet
    where = "/opt/texlive/texmf-dist/tex/generic/colorprofiles/sRGB.icc"
    data = subprocess.run(  # noqa: S603
        ["docker", "run", "--rm", compiler.image, "cat", where], check=True, capture_output=True
    ).stdout
    condition = OutputCondition("Acme_srgb.icc", identifier="ACME sRGB", info="sRGB", colorants=3)
    assert condition.check_profile(data) == []
    assert (
        OutputCondition("Acme_srgb.icc", identifier="x", info="y", colorants=4).check_profile(data)[0].code == "TM-C015"
    )
    intent = OutputIntent(condition, standards=(Standard.A2B,), language="en-GB", pdf_version="1.7")
    pkg = Package("acme-intent", prefix="ai")
    intent.declare(pkg)
    (tmp_path / "Acme_srgb.icc").write_bytes(data)
    (tmp_path / "acme-intent.sty").write_text(pkg.render())
    src = tmp_path / "doc.tex"
    src.write_text(pkg.document(Document(preamble=intent.slots())).replace(r"\begin{document}", "\\begin{document}\nx"))
    comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, roots=(tmp_path,))
    result = await comp.compile(src, tmp_path / "out")
    assert result.ok and result.pdf, result.diagnostics
    with pikepdf.open(result.pdf) as pdf:
        (found,) = pdf.Root.OutputIntents
        assert str(found.S) == "/GTS_PDFA1" and str(found.OutputConditionIdentifier) == "ACME sRGB"
    bare = Package("acme-bare", prefix="ab")  # the same document, the condition not registered
    (tmp_path / "acme-bare.sty").write_text(bare.render())
    plain = tmp_path / "bare.tex"
    plain.write_text(
        bare.document(Document(preamble=intent.slots())).replace(r"\begin{document}", "\\begin{document}\nx")
    )
    unregistered = await comp.compile(plain, tmp_path / "out2")
    assert unregistered.pdf
    with pikepdf.open(unregistered.pdf) as pdf:
        assert "/OutputIntents" not in pdf.Root  # the silent failure `declare` prevents
