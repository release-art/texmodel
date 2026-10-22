"""expl3 blocks through TeX (§21a 12): a block that compiles and exports what it declares, one that does not, and the
PDF Info route. Verification is by compiling; nothing here parses TeX."""

import pathlib

import pytest
from test_texmodel_build.test_compile_tex import compiler, fonts, require_files  # noqa: F401

from texmodel.body import Cs, Group, Hole, Lit, Seq, Syntax, TexRaw
from texmodel.components import Command
from texmodel.package import Package, PreambleSlots
from texmodel.preamble import PdfInfo, RequireMetadata
from texmodel.testing import export_probes
from texmodel.types import Raw
from texmodel_build.errors import CompileError
from texmodel_build.testkit import check_library, run_probes

from .test_pdf_string import CORPUS

pytestmark = [pytest.mark.tex, pytest.mark.timeout(300)]

FIT = r"""
    \fp_new:N \l__dm_size_fp
    \newcommand{\dmFit}[2]{ \fp_set:Nn \l__dm_size_fp { min ( 14 , max ( 8 , 12 * #2 / #1 ) ) } }
    \newcommand{\dmSize}{ \fp_eval:n { round ( \l__dm_size_fp , 1 ) } }
"""


def fit_package(block: str = FIT):
    pkg = Package("fit-demo", prefix="dm", version="1.0.0", date="2026/10/22")
    lib = pkg.library("sizing", block, syntax=Syntax.EXPL3)

    @pkg.command
    class Fit(Command):
        """Set the size from two numbers."""

        defined_by = lib
        width: Raw
        avail: Raw

    @pkg.command
    class Size(Command):
        """The size set last."""

        defined_by = lib

    return pkg, Fit, Size


def probes_of(comp, pkg, *nodes):  # noqa: ANN001, ANN201
    tex = pkg.test_document(*nodes, preamble=PreambleSlots(after_package=(Raw(export_probes(pkg)),)))
    sty = f"{pkg.name}.sty"
    return {m.name: m.value for m in run_probes(comp, tex, {sty: pkg.render()}, plans={sty: pkg.render_plan()})}


def test_a_valid_block_compiles_and_exports_what_it_declares(compiler):  # noqa: F811
    pkg, _, _ = fit_package()
    assert check_library(compiler, pkg) == []
    found = probes_of(compiler, pkg)
    assert found == {"def.dmFit": "yes", "arity.dmFit": "2", "def.dmSize": "yes", "arity.dmSize": "0"}


def test_a_component_the_block_does_not_define_is_reported_missing(compiler):  # noqa: F811
    pkg, _, _ = fit_package(FIT.replace("dmSize", "dmOther"))
    (missing,) = check_library(compiler, pkg)
    assert (missing.code, missing.path) == ("TM-C010", "Size")


def test_a_component_declared_with_another_arity_is_reported(compiler):  # noqa: F811
    pkg, _, _ = fit_package(FIT.replace("[2]", "[3]"))
    (wrong,) = check_library(compiler, pkg)
    assert (wrong.code, wrong.path) == ("TM-C011", "Fit") and "defines 3" in wrong.message


def test_a_name_that_is_not_a_plain_macro_is_checked_for_existence_only(compiler):  # noqa: F811
    pkg, _, _ = fit_package(
        FIT.replace("\\newcommand{\\dmSize}{ \\fp_eval:n { round ( \\l__dm_size_fp , 1 ) } }", "\\let\\dmSize\\relax")
    )
    assert probes_of(compiler, pkg)["arity.dmSize"] == "?" and check_library(compiler, pkg) == []


@pytest.mark.parametrize(
    "bad",
    [
        "\\fp_nosuch:n { 1 }\n",  # an undefined function
        "\\fp_set:Nn \\l_tmpa_fp\n",  # an argument missing: the next line is taken for it
        "\\cs_new:Npn \\dm_x:n #1 { #2 }\n",  # a parameter the definition does not have
    ],
)
def test_a_block_that_breaks_the_compile_names_itself_as_the_path(compiler, bad):  # noqa: F811
    pkg, _, _ = fit_package(bad + FIT)
    with pytest.raises(CompileError) as failed:
        check_library(compiler, pkg)
    errors = [d for d in failed.value.diagnostics if d.severity.value == "error"]
    assert errors and {d.path for d in errors} == {"sizing"}


def test_a_defined_component_called_from_a_generated_body_expands_in_tex(compiler):  # noqa: F811
    pkg, fit, size = fit_package()

    @pkg.command
    class Report(Command):
        """Sets the size and writes it to the log."""

        width: Raw
        avail: Raw

        def body(self):
            yield fit.call(Hole("width"), Hole("avail"))
            yield Seq(Cs("typeout"), Group(Lit("texmodel:probe:size="), size.call()))

    sty = {"fit-demo.sty": pkg.render()}
    cases = {("100", "100"): "12", ("100", "80"): "9.6", ("100", "50"): "8", ("100", "200"): "14"}
    nodes = [Report(Raw(w), Raw(a)) for w, a in cases]
    tex = pkg.test_document(*nodes)
    found = [
        m.value for m in run_probes(compiler, tex, sty, plans={"fit-demo.sty": pkg.render_plan()}) if m.name == "size"
    ]
    assert found == list(cases.values())


def test_an_expl3_body_writes_text_spaces_and_ignores_line_ends(compiler):  # noqa: F811
    pkg = Package("echo-demo", prefix="ed", version="1.0.0", date="2026/10/22")

    @pkg.command
    class Echo(Command):
        """Writes a line to the log; the body is expl3, where a space is `~`."""

        def body(self):
            yield TexRaw("\\typeout{texmodel:probe:echo=", syntax=Syntax.EXPL3)
            yield Lit("a b c")
            yield TexRaw("}", syntax=Syntax.EXPL3)

    found = run_probes(compiler, pkg.test_document(Echo()), {"echo-demo.sty": pkg.render()})
    assert [m.value for m in found if m.name == "echo"] == ["a b c"]


def test_pdf_info_entries_read_back_from_the_pdf(compiler, tmp_path: pathlib.Path):  # noqa: F811
    import pikepdf

    require_files(compiler, "tagpdf-base.sty")
    pkg = Package("info-kit", prefix="ik")
    entries = {f"K{'abcdefghijklmnop'[i]}": text for i, text in enumerate(CORPUS)}
    slots = PreambleSlots(before_class=(RequireMetadata(),), after_package=(PdfInfo(**entries),))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "info-kit.sty").write_text(pkg.render(), encoding="utf-8")
    (tmp_path / "src" / "d.tex").write_text(pkg.test_document(preamble=slots), encoding="utf-8")
    result = compiler.compile(tmp_path / "src" / "d.tex", tmp_path / "out")
    assert result.ok, [(x.message, x.code) for x in result.diagnostics]
    with pikepdf.open(result.pdf) as pdf:  # pyright: ignore[reportArgumentType]
        got = {k: str(pdf.docinfo[f"/{k}"]) for k in entries if f"/{k}" in pdf.docinfo}
    assert got == entries
