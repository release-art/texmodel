"""expl3 as a syntax mode and verbatim library blocks (§21): rendering, refusals and the static side of the exports.

The compile side (a block that TeX accepts or refuses, exports found in the log) is `test_expl3_tex.py`.
"""

import pathlib

import pytest
from hypothesis import (
    given,
    strategies as st,
)

from texmodel.body import Cs, Group, Hole, Library, Lit, Seq, Syntax, TemplateRef, TexRaw, Whitespace
from texmodel.components import Command, Environment
from texmodel.package import Package, PreambleSlots
from texmodel.plan import Plan
from texmodel.preamble import PdfInfo, RequireMetadata
from texmodel.testing import check_exports, export_probes
from texmodel.types import PdfString, Raw, Text, pdf_escape
from texmodel_build.diagnostics import Measurement
from texmodel_build.result import CompileResult
from texmodel_build.testkit import check_library

from .test_document import codes, refused

BLOCK = r"""

    \fp_new:N \l__dm_size_fp
    \newcommand{\dmFit}[2]{ \fp_set:Nn \l__dm_size_fp { #1 / ##1 } }

"""


def kit():
    pkg = Package("expl-demo", prefix="dm", version="1.0.0", date="2026/10/22")
    lib = pkg.library("sizing", BLOCK, syntax=Syntax.EXPL3)

    @pkg.command
    class Fit(Command):
        """Set the size from two widths; the block defines it."""

        defined_by = lib
        width: Raw
        avail: Raw

    return pkg, lib, Fit


# --- the syntax of a body ---------------------------------------------------------------------------------------


def test_the_syntaxes_are_a_closed_set():
    assert [s.value for s in Syntax] == ["latex2e", "expl3"]


def test_a_control_sequence_has_the_names_its_syntax_allows():
    assert Cs("fp_eval:n", Syntax.EXPL3).name == "fp_eval:n" and Cs("a@b").name == "a@b"
    with refused("TM-M027") as info:
        Cs("fp_eval:n")
    assert "letters and @ only" in str(info.value)
    with refused("TM-M027") as info:
        Cs("fp eval", Syntax.EXPL3)
    assert "letters, @, _ and : only" in str(info.value)


def test_a_component_names_its_control_sequence_in_the_syntax_it_declares():
    pkg = Package("cs-expl", prefix="")

    @pkg.command
    class Upper(Command):
        """An expl3-named command."""

        syntax = Syntax.EXPL3
        cs = "demo_upper:n"
        body = TexRaw(r"\text_uppercase:n { #text }", syntax=Syntax.EXPL3)
        text: Text

    assert Upper.__tm_cs__ == "demo_upper:n"
    with refused("TM-M027"):

        class Plain(Command):
            """The same name without saying so."""

            cs = "demo_upper:n"
            body = "x"
            text: Text


def test_an_expl3_body_is_wrapped_ignores_whitespace_and_writes_text_with_tilde():
    pkg = Package("body-expl", prefix="dm", version="1.0.0", date="2026/10/22", whitespace=Whitespace.TRIM)
    lib = pkg.library("sizing", BLOCK, syntax=Syntax.EXPL3)

    @pkg.command
    class Fit(Command):
        """Defined by the block."""

        defined_by = lib
        width: Raw
        avail: Text

    @pkg.command
    class Total(Command):
        """Total."""

        note: Text

        def body(self):
            yield Seq(Cs("par", Syntax.EXPL3), Lit("Total: "), Fit.call(Raw("1"), "a b"))
            yield TexRaw("  \\foo\n  \\bar", whitespace=Whitespace.TRIM, syntax=Syntax.EXPL3)
            yield Group(Hole("note"))

    assert pkg.render().split("(body: inline)\n")[1] == (
        "\\ExplSyntaxOn\n"
        "\\newcommand{\\dmTotal}[1]{\n"
        "\\par Total:~\\dmFit{1}{a~b}\n"
        "\\foo\n"
        "\\bar\n"
        "{#1}\n"
        "}\n"
        "\\ExplSyntaxOff\n"
    )


def test_an_expl3_environment_has_one_syntax_over_both_bodies():
    pkg = Package("env-expl", prefix="dm")

    @pkg.environment
    class Box(Environment):
        """A box."""

        children = []
        begin = TexRaw(r"\begin{center}", syntax=Syntax.EXPL3)
        end = TexRaw(r"\end{center}", syntax=Syntax.EXPL3)

    assert (
        "\\ExplSyntaxOn\n\\newenvironment{dmBox}{\n\\begin{center}\n}{\n\\end{center}\n}\n\\ExplSyntaxOff"
        in pkg.render()
    )
    with refused("TM-M031") as info:

        class Mixed(Environment):
            """The begin is expl3, the end is not."""

            children = []
            begin = TexRaw(r"\begin{center}", syntax=Syntax.EXPL3)
            end = r"\end{center}"

        pkg.environment(Mixed)
    assert info.value.path == "Mixed" and "expl3 and latex2e" in str(info.value)


def test_pieces_of_two_syntaxes_in_one_body_are_refused_with_the_component(tmp_path: pathlib.Path):
    pkg = Package("mix-expl", prefix="dm")
    (tmp_path / "t.tex").write_text("x", encoding="utf-8")
    for pieces in (
        [TexRaw("a", syntax=Syntax.EXPL3), "b"],
        [Seq(Cs("a", Syntax.EXPL3), Group(Cs("b")))],
        [TemplateRef(tmp_path / "t.tex", syntax=Syntax.EXPL3), TexRaw("b")],
    ):
        with refused("TM-M031"):

            class Mixed(Command):
                """Mixed."""

                body = pieces

            pkg.command(Mixed)


def test_a_template_ref_carries_its_syntax_into_the_body(tmp_path: pathlib.Path):
    (tmp_path / "t.tex").write_text("\\foo  bar\n", encoding="utf-8")
    pkg = Package("tpl-expl", prefix="dm")

    @pkg.command
    class Shown(Command):
        """From a file."""

        body = TemplateRef(tmp_path / "t.tex", syntax=Syntax.EXPL3)

    assert "\\ExplSyntaxOn\n\\newcommand{\\dmShown}{\n\\foo  bar\n}\n\\ExplSyntaxOff" in pkg.render()


def test_a_text_argument_of_a_call_in_an_expl3_body_writes_its_spaces_as_tilde():
    pkg = Package("arg-expl", prefix="dm")

    @pkg.command
    class Say(Command):
        """Takes text, a PDF string and a raw argument."""

        body = "#text #pdf #raw"
        text: Text
        pdf: PdfString
        raw: Raw

    @pkg.command
    class Use(Command):
        """Calls it."""

        body = Seq(Cs("relax", Syntax.EXPL3), Say.call("a & b", "x (y)", Raw("c d")))

    assert "\\relax\\dmSay{a~\\&~b}{\\detokenize{x~\\050y\\051}}{c d}" in pkg.render()


# --- library blocks ---------------------------------------------------------------------------------------------


def test_a_block_is_written_as_given_between_the_syntax_switches():
    pkg, lib, _ = kit()
    assert isinstance(lib, Library) and lib.syntax is Syntax.EXPL3 and lib.origin == "inline"
    assert pkg.render(version="1.2.3") == (
        "% expl-demo.sty -- generated with texmodel 1.2.3. Do not edit; run `texmodel build`.\n"
        "\\NeedsTeXFormat{LaTeX2e}\n"
        "\\ProvidesPackage{expl-demo}[2026/10/22 v1.0.0 expl-demo]\n"
        "\n"
        "% from library sizing (source: inline)\n"
        "\\ExplSyntaxOn\n"
        "\\fp_new:N \\l__dm_size_fp\n"
        "\\newcommand{\\dmFit}[2]{ \\fp_set:Nn \\l__dm_size_fp { #1 / ##1 } }\n"
        "\\ExplSyntaxOff\n"
    )


def test_a_latex2e_block_is_not_wrapped_and_blocks_keep_registration_order_among_items():
    pkg = Package("order-demo", prefix="od", version="1.0.0", date="2026/10/22")

    @pkg.command
    class First(Command):
        """First."""

        body = "a"

    pkg.library("middle", "\\makeatletter\n  \\def\\x{1}\n  \\makeatother\n")

    @pkg.command
    class Last(Command):
        """Last."""

        body = "b"

    plan = pkg.render_plan()
    assert [p for p, _ in dict.fromkeys((x.path, 0) for x in plan.lines)] == [
        "header",
        "requires",
        "First",
        "middle",
        "Last",
    ]
    assert (
        "% from library middle (source: inline)\n\\makeatletter\n  \\def\\x{1}\n  \\makeatother\n\n% Last."
        in pkg.render()
    )


def test_every_line_of_a_block_has_the_blocks_name_as_its_path():
    pkg, _, _ = kit()
    lines = [x.tex for x in pkg.render_plan().lines if x.path == "sizing"]
    assert lines[0] == "% from library sizing (source: inline)" and lines[1] == "\\ExplSyntaxOn"
    assert lines[-1] == "\\ExplSyntaxOff" and len(lines) == 5


@given(st.lists(st.sampled_from(["#1", "##1", "#", "\\#", "%", "\\%", "{x}", "\n", "\\foo", "a_b:n"]), max_size=12))
def test_a_block_is_never_rewritten(parts):
    """`#name` rewriting is for bodies: a block's text comes out as it went in, with only the edges trimmed."""
    text = "".join(parts)
    pkg = Package("law-demo", prefix="ld")
    lib = pkg.library("law", text)
    assert lib.text == text.strip("\n") and lib.text in pkg.render()


def test_a_block_may_come_from_a_template_file(tmp_path: pathlib.Path):
    pkg = Package("file-demo", prefix="fd")
    absolute = tmp_path / "abs.tex"
    absolute.write_text("\n\\def\\a{#1}\n", encoding="utf-8")
    assert pkg.library("absolute", TemplateRef(absolute)).text == "\\def\\a{#1}"
    near = pkg.library("near", TemplateRef("block.tex"), syntax=Syntax.EXPL3)  # relative to this module
    assert near.origin == "block.tex" and near.text == "\\cs_new:Npn \\demo_near:n #1 { #1 }"
    with refused("TM-M005") as info:
        pkg.library("gone", TemplateRef(tmp_path / "missing.tex"))
    assert info.value.path == "gone"


def test_a_block_is_refused_for_its_name_braces_or_syntax_switch():
    pkg = Package("refuse-demo", prefix="rd")
    pkg.library("one", "\\relax")
    with refused("TM-M007") as info:
        pkg.library("one", "\\relax")
    assert info.value.path == "one"
    with refused("TM-M001"):
        pkg.library("1 bad", "\\relax")
    with refused("TM-M011") as info:
        pkg.library("open", "\\def\\a{")
    assert info.value.path == "open"
    pkg.library("comment", "% }\n\\relax")  # a brace in a comment is no brace
    for text in ("\\ExplSyntaxOn\n\\relax", "\\relax\\ExplSyntaxOff", "\\relax % x\n\\ExplSyntaxOn"):
        with refused("TM-M034") as info:
            pkg.library("switch", text, syntax=Syntax.EXPL3)
        assert info.value.path == "switch"
    pkg.library("fine", "% \\ExplSyntaxOn is written by texmodel\n\\relax \\% \\ExplSyntaxOnly", syntax=Syntax.EXPL3)
    pkg.library("plain", "\\ExplSyntaxOn\n\\ExplSyntaxOff")  # a latex2e block may switch syntax itself


# --- a component a block defines --------------------------------------------------------------------------------


def test_a_defined_component_is_declared_claims_its_name_and_renders_no_definition():
    pkg, _, fit = kit()
    assert "\\newcommand{\\dmFit}[2]{ \\fp_set" in pkg.render() and pkg.render().count("dmFit}") == 1
    assert fit.__tm_cs__ == "dmFit" and fit.__tm_package__ is pkg
    assert fit.call(Raw("1"), Raw("2")).values == (Raw("1"), Raw("2"))
    with refused("TM-M026"):
        fit.call(Raw("1"))  # arity-checked
    with refused("TM-M007"):

        @pkg.command
        class Again(Command):
            """The same control sequence."""

            cs = "dmFit"
            body = "x"


def test_a_defined_environment_is_the_same():
    pkg = Package("env-block", prefix="eb")
    lib = pkg.library("box", "\\newenvironment{ebBox}[1]{\\begin{center}#1}{\\end{center}}")

    @pkg.environment
    class Box(Environment):
        """Defined by the block."""

        defined_by = lib
        children = []
        title: Text

    assert pkg.render().count("ebBox") == 1 and Box.open(title="t").kind.value == "open"


def test_a_defined_component_has_no_body_and_belongs_to_the_package_of_its_block():
    pkg, lib, _ = kit()
    with refused("TM-M032") as info:

        @pkg.command
        class Both(Command):
            """A body as well."""

            defined_by = lib
            body = "x"

    assert info.value.path == "Both"
    other = Package("other-demo", prefix="ot")
    with refused("TM-M033") as info:

        @other.command
        class Foreign(Command):
            """Someone else's block."""

            defined_by = lib

    assert info.value.path == "Foreign"
    with refused("TM-M032"):

        @pkg.environment
        class Box(Environment):
            """A body as well."""

            defined_by = lib
            children = []
            begin = "x"
            end = "y"


# --- the exports ------------------------------------------------------------------------------------------------


def test_export_probes_name_each_defined_component_and_are_empty_without_one():
    pkg, _, _ = kit()
    probes = export_probes(pkg)
    assert probes.splitlines()[-1] == "\\tmexport{dmFit}" and "texmodel:probe:def.#1=yes" in probes
    assert export_probes(Package("none-demo", prefix="nd")) == ""


def test_exports_are_checked_for_existence_and_arity():
    pkg, _, _ = kit()
    assert check_exports(pkg, {"def.dmFit": "yes", "arity.dmFit": "2"}) == []
    assert check_exports(pkg, {"def.dmFit": "yes", "arity.dmFit": "?"}) == []  # not a plain macro: existence only
    (missing,) = check_exports(pkg, {"def.dmFit": "no"})
    assert (missing.code, missing.path) == ("TM-C010", "Fit") and "sizing" in missing.message
    assert [v.code for v in check_exports(pkg, {})] == ["TM-C010"]
    (wrong,) = check_exports(pkg, {"def.dmFit": "yes", "arity.dmFit": "3"})
    assert (
        (wrong.code, wrong.path) == ("TM-C011", "Fit")
        and "declared 2" in wrong.message
        and "defines 3" in wrong.message
    )


def test_an_optional_argument_counts_in_the_declared_arity():
    pkg = Package("opt-demo", prefix="op")
    lib = pkg.library("opt", "\\newcommand{\\opNote}[2][x]{#2}")

    @pkg.command
    class Note(Command):
        """Defined by the block."""

        defined_by = lib
        text: Text
        kind: Text | None = None

    assert check_exports(pkg, {"def.opNote": "yes", "arity.opNote": "2"}) == []
    assert [v.code for v in check_exports(pkg, {"def.opNote": "yes", "arity.opNote": "1"})] == ["TM-C011"]


# --- PdfInfo ----------------------------------------------------------------------------------------------------


def test_pdf_info_writes_each_entry_through_pdfmanagement():
    info = PdfInfo(Title="Rex (the fox)", Author="A & B")
    assert info.raw().tex == (
        "\\csname pdfmanagement_add:nnn\\endcsname{Info}{Title}{(\\detokenize{Rex \\050the fox\\051})}\n"
        "\\csname pdfmanagement_add:nnn\\endcsname{Info}{Author}{(\\detokenize{A \\046 B})}"
    )
    with refused("TM-M035") as failed:
        PdfInfo(**{"Bad Key": "x"})
    assert failed.value.path == "PdfInfo"


@given(st.text(max_size=40))
def test_a_pdf_info_value_is_the_pdf_escaped_text(value):
    assert f"{{(\\detokenize{{{pdf_escape(value)}}})}}" in PdfInfo(Title=value).raw().tex


def test_a_document_with_pdf_info_needs_metadata_before_the_class():
    pkg = Package("info-doc", prefix="id")
    managed = PreambleSlots(before_class=(RequireMetadata(),), after_package=(PdfInfo(Title="Rex"),))
    text = pkg.document(preamble=managed)
    assert text.index("\\DocumentMetadata") < text.index("pdfmanagement_add:nnn") < text.index("\\begin{document}")
    assert "\\detokenize{Rex}" in pkg.document(
        preamble=PreambleSlots(before_class=(RequireMetadata(),), before_package=(PdfInfo(Title="Rex"),))
    )
    bare = PreambleSlots(before_package=(PdfInfo(Title="a"),), after_package=(PdfInfo(Title="b"),))
    with pytest.raises(ExceptionGroup) as group:
        pkg.document(preamble=bare)
    assert codes(group) == ["TM-C009", "TM-C009"]
    assert [getattr(e, "path") for e in group.value.exceptions]  # noqa: B009 == ["preamble.before_package[0]", "preamble.after_package[0]"]
    with pytest.raises(ExceptionGroup) as group:
        pkg.document(preamble=PreambleSlots(before_class=(RequireMetadata(), PdfInfo(Title="a"))))
    assert codes(group) == ["TM-C008"]  # the slot is wrong as well; before_class holds the metadata


def test_a_plan_of_a_document_with_pdf_info_names_the_entry():
    plan: Plan = Package("info-plan", prefix="ip").plan(
        preamble=PreambleSlots(before_class=(RequireMetadata(),), after_package=(PdfInfo(Title="a", Author="b"),))
    )
    assert [x.path for x in plan.lines if "pdfmanagement" in x.tex] == ["preamble.after_package[0]"] * 2


# --- check_library without TeX ----------------------------------------------------------------------------------


class FakeCompiler:
    """Stands in for `Compiler`: records what it was given and answers with the probes it was told to."""

    def __init__(self, probes: dict[str, str]) -> None:
        self.probes, self.seen = probes, {}

    def compile(self, source: pathlib.Path, outdir: pathlib.Path, *, plans: dict[str, Plan] | None = None):  # noqa: ANN201
        self.seen = {"tex": source.read_text(), "sty": (source.parent / "expl-demo.sty").read_text(), "plans": plans}
        found = tuple(Measurement(message="", name=n, value=v) for n, v in self.probes.items())
        return CompileResult(
            pdf=pathlib.Path("x.pdf"), log=None, passes=1, pages=1, diagnostics=found, seconds=0.0,
            engine="lualatex", engine_version="", latexmk_version="",
        )  # fmt: skip


def test_check_library_compiles_the_package_with_the_export_probes_and_reads_them_back():
    pkg, _, _ = kit()
    good = FakeCompiler({"def.dmFit": "yes", "arity.dmFit": "2"})
    assert check_library(good, pkg) == []  # type: ignore[arg-type]
    assert "\\tmexport{dmFit}" in good.seen["tex"] and good.seen["sty"] == pkg.render()
    assert good.seen["plans"] == {"expl-demo.sty": pkg.render_plan()}
    bad = FakeCompiler({"def.dmFit": "yes", "arity.dmFit": "3"})
    assert [v.code for v in check_library(bad, pkg, {"other.sty": "x"})] == ["TM-C011"]  # type: ignore[arg-type]
