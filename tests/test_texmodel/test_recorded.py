"""`texmodel.ext.recorded`: a value only the whole document knows, carried between runs, and the folds that make it."""

import dataclasses

import pytest
from hypothesis import (
    given,
    strategies as st,
)
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.ext.recorded import APPEND, LENGTHS, MAX, MIN, SUM, Fold, Recorded
from texmodel.package import Package
from texmodel.run.compiler import Compiler
from texmodel.run.diagnostics import Measurement
from texmodel.run.testkit import check_library
from texmodel.types import Length, Raw

pkg = Package("acme-rec", prefix="ar")
LABEL = Recorded("LabelWidth")
CARDS = Recorded("Cards", kind=int, fold=SUM)
FEWEST = Recorded("Fewest", kind=int, fold=MIN)
WIDTHS = Recorded("Widths", kind=LENGTHS, fold=APPEND)
PARTS = {r.name: r.declare(pkg) for r in (LABEL, CARDS, FEWEST, WIDTHS)}


def test_declare_registers_the_block_the_command_and_the_value():
    record, value = PARTS["LabelWidth"]
    assert record.__name__ == "RecordLabelWidth" and value.__name__ == "LabelWidth"
    sty = pkg.render()
    assert r"\newcommand{\arRecordLabelWidth}[1]{%" in sty and r"\newlength{\arLabelWidth}" in sty
    assert r"\newcommand{\arCards}{0}" in sty and r"\newcount{\ar@recCardsseen}" in sty  # an int: a macro, a count
    assert r"\providecommand\string\ar@recLabelWidthread[1]{}" in sty  # the .aux defends itself
    assert pkg.check_parts() == []
    assert record(value=Raw("12pt")).render() == r"\arRecordLabelWidth{12pt}"
    assert r"\arRecordLabelWidth{3pt}" in pkg.document(record(value=Raw("3pt")))


def test_the_update_and_refresh_follow_the_fold():
    sty = pkg.render()
    assert r"\ifdim#1>\ar@recLabelWidthseen\global\ar@recLabelWidthseen=#1\relax\fi" in sty  # MAX of a length
    assert r"\global\advance\ar@recCardsseen by #1\relax" in sty  # SUM
    assert r"\ifnum#1<\ar@recFewestseen\global\ar@recFewestseen=#1\relax\fi" in sty  # MIN of an int
    # idempotent folds take the last run's value into this run; a sum reports that value alone
    assert r"\global\arLabelWidth=\ar@recLabelWidthlast\relax\ifdim\ar@recLabelWidthseen>\arLabelWidth" in sty
    assert r"\global\count@=\ar@recCardslast\relax\xdef\arCards{\the\count@}" in sty
    assert r"\ifnum\ar@recFewestseen<\count@\global\count@=\ar@recFewestseen\relax\fi\xdef\arFewest" in sty


@pytest.mark.parametrize(
    "args",
    [
        {"name": "label"},
        {"name": "Label2"},
        {"name": "A_B"},
        {"name": ""},
    ],
)
def test_a_name_that_is_not_letters_is_refused(args):
    with pytest.raises(DeclarationError) as raised:
        Recorded(**args)
    assert raised.value.code == "TM-M056"


def test_a_kind_a_fold_does_not_take_and_a_package_with_no_prefix_are_refused():
    with pytest.raises(DeclarationError) as raised:
        Recorded("X", kind=float)  # type: ignore[arg-type]
    assert raised.value.code == "TM-M057"
    no_length = dataclasses.replace(MAX, update={int: MAX.update[int]}, identity={int: "0"})
    with pytest.raises(DeclarationError) as raised:
        Recorded("X", fold=no_length)
    assert raised.value.code == "TM-M058"
    with pytest.raises(DeclarationError) as raised:
        Recorded("X").declare(Package("bare", prefix=""))
    assert raised.value.code == "TM-M059"
    with pytest.raises(DeclarationError):
        LABEL.declare(pkg)  # a block is declared once


values = st.lists(st.integers(min_value=0, max_value=10_000), max_size=12)


@pytest.mark.parametrize("fold", [MAX, MIN, SUM], ids=lambda f: f.name)
@given(xs=values, seed=st.randoms(use_true_random=False))
def test_a_fold_does_not_depend_on_the_order(fold, xs, seed):
    shuffled = list(xs)
    seed.shuffle(shuffled)
    assert fold.reduce(shuffled) == fold.reduce(xs)


@pytest.mark.parametrize("fold", [MAX, MIN], ids=lambda f: f.name)
@given(xs=values)
def test_an_idempotent_fold_takes_a_value_twice_as_once(fold, xs):
    assert fold.idempotent and fold.reduce([*xs, *xs]) == fold.reduce(xs)


def test_a_list_keeps_its_order_and_is_not_idempotent():
    assert APPEND.reduce([3, 1, 2]) == [3, 1, 2] and APPEND.reduce([1, 1]) == [1, 1]
    assert not APPEND.idempotent and tuple(APPEND.update) == (LENGTHS,)
    sty = pkg.render()
    assert r"\xdef\ar@recWidthsseen{\ifx\ar@recWidthsseen\@empty\else\ar@recWidthsseen,\fi\the\dimexpr#1\relax}" in sty
    assert r"\xdef\arWidths{\ar@recWidthslast}" in sty and r"str_if_eq:eeTF" in sty  # strings, not catcodes
    with pytest.raises(DeclarationError) as raised:
        Recorded("Bad", kind=LENGTHS)  # MAX does not take a list
    assert raised.value.code == "TM-M058"
    with pytest.raises(DeclarationError) as raised:
        Recorded("Bad", kind=Length, fold=APPEND)
    assert raised.value.code == "TM-M058"


def test_a_sum_is_not_idempotent_and_the_identities_change_nothing():
    assert not SUM.idempotent and SUM.reduce([2, 2]) != SUM.reduce([2])
    for fold, identity in ((MAX, 0), (SUM, 0), (MIN, float("inf"))):
        assert fold.reduce([5, identity]) == fold.reduce([5])
    assert isinstance(MAX, Fold)


CASES = {
    "LabelWidth": ([12, 30, 20], 30),
    "Cards": ([1, 1, 1, 1], 4),
    "Fewest": ([9, 3, 5], 3),
    "Widths": ([12, 30, 20], "12.0pt,30.0pt,20.0pt"),
}


def document_tex(package):
    body = []
    for name, (xs, _) in CASES.items():
        unit = "pt" if name in ("LabelWidth", "Widths") else ""
        body += [rf"\arRecord{name}{{{x}{unit}}}" for x in xs]
    use = {"LabelWidth": r"\the\ar", "Cards": r"\ar", "Fewest": r"\ar", "Widths": r"\ar"}  # a macro: no `\the`
    probes = "".join(rf"\typeout{{texmodel:probe:{{}}{n}={use[n]}{n}}}" for n in CASES)
    start = probes.replace("{}", "start-")
    end = probes.replace("{}", "end-")
    tex = package.document(Document())
    return tex.replace(r"\begin{document}", "\\begin{document}\n" + start + "".join(body) + end + "x")


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_the_value_settles_over_two_runs_and_the_tex_agrees_with_python(compiler, tmp_path):  # noqa: F811
    (tmp_path / "acme-rec.sty").write_text(pkg.render())
    src = tmp_path / "doc.tex"
    src.write_text(document_tex(pkg))
    comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, roots=(tmp_path,))
    result = await comp.compile(src, tmp_path / "out")
    assert result.ok and result.passes >= 1, result.diagnostics
    found = {m.name: m.value for m in result.diagnostics if isinstance(m, Measurement)}
    fold_of = {"LabelWidth": MAX, "Cards": SUM, "Fewest": MIN, "Widths": APPEND}
    for name, (xs, expected) in CASES.items():
        text = found[f"end-{name}"]
        if name == "Widths":  # a list is the last run's, in order, as the .aux spelled it
            assert APPEND.reduce(xs) == xs and text == expected
            continue
        assert fold_of[name].reduce(xs) == expected
        assert float(text.removesuffix("pt")) == expected if name == "LabelWidth" else int(text) == expected
        # what the final run read from the .aux before any card was recorded: the value, carried between runs
        assert found[f"start-{name}"] == found[f"end-{name}"]
    assert not [d for d in result.diagnostics if getattr(d, "code", "") == "TM-X019"]  # nothing left unsettled


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_the_library_defines_what_it_declares(compiler):  # noqa: F811
    assert await check_library(compiler, pkg) == []


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_an_aux_line_the_installed_package_does_not_know_is_swallowed(compiler, tmp_path):  # noqa: F811
    (tmp_path / "acme-rec.sty").write_text(pkg.render())
    src = tmp_path / "doc.tex"
    src.write_text(document_tex(pkg))
    comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, roots=(tmp_path,))
    assert (await comp.compile(src, tmp_path / "out")).ok  # writes the .aux
    bare = Package("acme-rec", prefix="ar")
    (tmp_path / "acme-rec.sty").write_text(bare.render())
    src.write_text(bare.document(Document()).replace(r"\end{document}", "x\n\\end{document}"))  # a page
    again = await comp.compile(src, tmp_path / "out")  # the .aux still has the lines, the package has not the macros
    assert again.ok, again.diagnostics
