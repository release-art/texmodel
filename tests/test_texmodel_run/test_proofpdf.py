import builtins
import pathlib

import pikepdf
import pytest

from texmodel.run import testkit
from texmodel.run._internal.proofpdf import ProofPdf
from texmodel.run.diagnostics import Severity
from texmodel.run.verify import Profile, registered, verify_file


@pytest.fixture
def pdf(tmp_path) -> pathlib.Path:
    path = tmp_path / "a.pdf"
    doc = pikepdf.new()
    doc.add_blank_page(page_size=(200, 300))
    doc.save(path)
    return path


# PDF/A and colour need external tools; the PDF/X structure layer is in-process.
STRUCTURE = {"pdfa": False, "colour": False}


async def test_the_adapter_runs_proof_pdfs_in_process_checks(pdf):
    report = await verify_file(pdf, Profile(checks=("proof-pdf",), options={"proof-pdf": STRUCTURE}), registered())
    assert not report.ok  # a bare page has no PDF/X-4 identity
    assert {f.check for f in report.findings}
    assert all(f.severity in (Severity.ERROR, Severity.WARNING) for f in report.findings)


async def test_options_map_onto_proof_pdfs_profile(pdf):
    options = {
        **STRUCTURE,
        "geometry": {"trim_w_mm": 50, "trim_h_mm": 50, "bleed_mm": 3},
        "allow_spots": ["Dieline"],
        "proof_profile": "p.icc",
    }
    findings = await ProofPdf().verify(pdf, options)
    assert any("trim" in f.message.lower() or "box" in f.message.lower() for f in findings)


def test_missing_tools_and_bad_options_are_unconfirmable(monkeypatch):
    from proof_pdf import core

    monkeypatch.setattr(core, "missing_tools", lambda profile: ["verapdf", "gs"])
    assert ProofPdf().unavailable({}) == "missing tools: verapdf, gs"
    assert "bad proof-pdf options" in (ProofPdf().unavailable({"bogus": 1}) or "")
    monkeypatch.setattr(core, "missing_tools", lambda profile: [])
    assert ProofPdf().unavailable(STRUCTURE) is None


def test_without_proof_pdf_installed_the_verifier_fails_closed(monkeypatch):
    real = builtins.__import__

    def deny(name, *args, **kwargs):
        if name.startswith("proof_pdf"):
            raise ImportError(name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny)
    assert "pip install 'texmodel[proof-pdf]'" in (ProofPdf().unavailable({}) or "")


async def test_the_adapter_passes_the_plugin_contract(tmp_path):
    await testkit.check_verifier_contract(ProofPdf(), tmp_path)
