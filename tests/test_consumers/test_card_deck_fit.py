"""The synthetic deck's expl3 algorithm (§21): carried verbatim, defined as declared, and giving the right sizes."""

import pytest
from card_deck import fit
from test_texmodel_build.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.types import Raw
from texmodel_build.testkit import check_library, run_probes

SIZES = {("100pt", "100pt"): "12", ("100pt", "80pt"): "9.6", ("100pt", "50pt"): "8", ("100pt", "200pt"): "14"}


def test_the_block_is_carried_as_written_between_the_syntax_switches():
    block = [x.tex for x in fit.pkg.render_plan().lines if x.path == "title-size"]
    assert block[:3] == [
        "% from library title-size (source: inline)",
        "\\ExplSyntaxOn",
        "% A title of natural width #1 set in a space of width #2: 12pt scaled to fit, between 8pt and 14pt.",
    ]
    assert (
        "    \\fp_set:Nn \\l__cf_size_fp { min ( 14 , max ( 8 , 12 * \\dim_to_fp:n { #2 } / \\dim_to_fp:n { #1 } ) ) }"
        in block
    )
    assert (
        block[-1] == "\\ExplSyntaxOff"
        and "\\newcommand{\\cfFitSize}" not in fit.pkg.render().split("\n\n% Work out")[1]
    )


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_the_block_defines_what_the_components_declare(compiler):  # noqa: F811
    assert check_library(compiler, fit.pkg) == []


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_the_title_size_is_the_fitted_size_between_the_limits(compiler):  # noqa: F811
    nodes = [fit.ShowTitleSize(natural=Raw(n), available=Raw(a)) for n, a in SIZES]
    tex = fit.pkg.test_document(*nodes)
    found = run_probes(compiler, tex, {"card-deck-fit.sty": fit.pkg.render()})
    assert [m.value for m in found if m.name == "title-size"] == list(SIZES.values())
