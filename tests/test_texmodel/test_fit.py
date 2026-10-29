"""`texmodel.ext.fit`: titles fitted to a band at sizes shared across the document, and the rule in Python."""

import math

import pytest
from hypothesis import (
    given,
    strategies as st,
)
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.ext.fit import Fit, choose_sizes
from texmodel.package import Package, declared
from texmodel.run.compiler import Compiler
from texmodel.run.diagnostics import Measurement
from texmodel.run.testkit import check_library
from texmodel.types import Length, Raw

pkg = Package("acme-fit", prefix="af")
FIT = Fit("Title", target=Length("12mm"), floor=Length("3mm"), room=Length("12mm"), treatment=Raw(r"\textbf{#1}"))
PARTS = FIT.declare(pkg)


def test_declare_registers_the_commands_the_values_and_the_three_records():
    assert [c.__name__ for c in (PARTS.record, PARTS.fit)] == ["RecordTitle", "FitTitle"]
    sty = pkg.render()
    for name in ("RecordTitleWidths", "RecordTitleAscent", "RecordTitleDescent", "TitleTarget", "TitleFloor"):
        assert name in {c.__name__ for c in pkg.registered}
    assert r"\newcommand{\afRecordTitle}[1]{%" in sty and r"\newcommand{\afFitTitle}[2]{%" in sty
    assert r"\cs_new:Npn \af_Title_treat:n #1 { \textbf{#1} }" in sty
    assert r"\setlength{\afTitleTarget}{12mm}" in sty and r"\int_compare:nNnTF { 2 } = { 0 }" in sty
    assert pkg.check_parts() == []


def test_the_scanner_reads_the_lengths_a_fit_declares():
    assert {"afTitleSize", "afTitleLineSize"} <= declared(pkg.render())


@pytest.mark.parametrize(
    ("args", "code"),
    [
        ({"name": "title"}, "TM-M060"),
        ({"reduced_sizes": 3}, "TM-M061"),
        ({"reduced_sizes": -1}, "TM-M061"),
        ({"floor": Length("9mm")}, "TM-M062"),
        ({"room": Length("0mm")}, "TM-M062"),
        ({"reference": Length("-1mm")}, "TM-M062"),
    ],
)
def test_a_declaration_that_cannot_work_is_refused(args, code):
    given_ = {"name": "Title", "target": Length("8mm"), "floor": Length("3mm"), "room": Length("12mm")} | args
    with pytest.raises(DeclarationError) as raised:
        Fit(**given_)
    assert raised.value.code == code


def test_a_package_with_no_prefix_cannot_declare_one():
    with pytest.raises(DeclarationError) as raised:
        FIT.declare(Package("bare", prefix=""))
    assert raised.value.code == "TM-M063"


fits = st.lists(st.floats(min_value=1, max_value=20, allow_nan=False), min_size=1, max_size=12)
GOAL = {"target": 8.0, "floor": 3.0}


@pytest.mark.parametrize("reduced", [0, 1, 2])
@given(each=fits)
def test_every_size_is_within_the_floor_and_the_title_own_fit(reduced, each):
    for own in each:
        size, line = choose_sizes(each, own, reduced_sizes=reduced, **GOAL)
        assert size >= GOAL["floor"] and line >= GOAL["floor"]
        assert size <= max(own, GOAL["floor"]) + 1e-9  # never larger than the title's own fit


@pytest.mark.parametrize("reduced", [1, 2])
@given(each=fits)
def test_titles_that_reach_the_target_share_one_size_and_the_rest_at_most_the_reduced_sizes(reduced, each):
    sizes = [choose_sizes(each, own, reduced_sizes=reduced, **GOAL) for own in each]
    reaching = {s for (s, _), own in zip(sizes, each, strict=True) if own >= GOAL["target"]}
    assert len(reaching) <= 1  # one main size
    shared = {s for (s, line), own in zip(sizes, each, strict=True) if own < GOAL["target"]}
    assert len(shared) <= reduced  # a title that cannot reach the target draws from at most this many sizes


@given(each=fits)
def test_zero_reduced_sizes_is_one_size_for_every_title(each):
    sizes = {choose_sizes(each, own, reduced_sizes=0, **GOAL)[0] for own in each}
    assert len(sizes) <= 2  # the main size, or the lowest fit that no title reaches the target with


def test_the_rule_on_a_known_deck():
    each = [12.0, 9.0, 8.0, 6.0, 5.5, 3.5]  # three reach the target 8, three do not
    assert choose_sizes(each, 12.0, reduced_sizes=2, **GOAL) == (8.0, 8.0)  # the main size: the smallest that reaches
    # the shorts are 6, 5.5, 3.5: splitting after two (j * (o_j - o_n) = 4) beats after one (2.5): upper group at 5.5
    assert choose_sizes(each, 6.0, reduced_sizes=2, **GOAL) == (5.5, 8.0)
    assert choose_sizes(each, 5.5, reduced_sizes=2, **GOAL) == (5.5, 8.0)
    assert choose_sizes(each, 3.5, reduced_sizes=2, **GOAL) == (3.5, 8.0)  # the lower group
    assert choose_sizes(each, 3.5, reduced_sizes=1, **GOAL)[0] == 3.5  # one shared size: the lowest
    assert choose_sizes(each, 12.0, reduced_sizes=0, **GOAL) == (3.5, 3.5)  # one size, set by the narrowest
    assert choose_sizes([], 6.0, reduced_sizes=2, **GOAL) == (6.0, 6.0)  # nothing recorded: fitted to itself
    assert choose_sizes([20.0], 20.0, reduced_sizes=2, target=8.0, floor=3.0) == (20.0, 20.0)
    assert choose_sizes([2.0], 2.0, reduced_sizes=2, **GOAL) == (3.0, 3.0)  # the floor binds
    assert math.isfinite(choose_sizes([1.0], 1.0, reduced_sizes=2, **GOAL)[0])


TITLES = [
    "Owl",
    "Great Spotted Woodpecker",
    "Red Kite",
    "Common Sandpiper",
    "Wren",
    "Lesser Spotted Woodpecker",
    "Black-Necked Grebe in Breeding Plumage",
    "Eurasian Oystercatcher Chick",
    "An Improbably Long Name for a Bird That Does Not Exist In Any Field Guide Whatever",
]


def document_tex():
    names = [f"t{i}" for i, _ in enumerate(TITLES)]
    records = "".join(rf"\afRecordTitle{{{t}}}" for t in TITLES)
    probe = r"\typeout{texmodel:probe:%s=\the\afTitleSize}"
    fits = "".join(rf"\afFitTitle{{{n}}}{{{t}}}" + (probe % n) + r"\par" for n, t in zip(names, TITLES, strict=True))
    facts = (
        r"\typeout{texmodel:probe:widths=\afTitleWidths}\typeout{texmodel:probe:ascent=\the\afTitleAscent}"
        r"\typeout{texmodel:probe:descent=\the\afTitleDescent}\typeout{texmodel:probe:line=\the\linewidth}"
        r"\typeout{texmodel:probe:main=\the\afTitleLineSize}"
    )
    return pkg.document(Document()).replace(r"\begin{document}", "\\begin{document}\n" + records + fits + facts + "x")


def points(text):
    return float(text.removesuffix("pt"))


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_the_tex_chooses_what_the_python_rule_chooses(compiler, tmp_path):  # noqa: F811
    (tmp_path / "acme-fit.sty").write_text(pkg.render())
    src = tmp_path / "doc.tex"
    src.write_text(document_tex())
    comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, roots=(tmp_path,))
    result = await comp.compile(src, tmp_path / "out")
    assert result.ok, result.diagnostics
    found = {m.name: m.value for m in result.diagnostics if isinstance(m, Measurement)}
    ref, room, floor, target = (Length(x).inches * 72.27 for x in ("10mm", "12mm", "3mm", "12mm"))
    cap = ref * room / (points(found["ascent"]) + points(found["descent"]))
    line = points(found["line"])
    each = [min(ref * line / points(w), cap) for w in found["widths"].split(",")]
    assert len(each) == len(TITLES)
    chosen = [points(found[f"t{i}"]) for i in range(len(TITLES))]
    for own, got in zip(each, chosen, strict=True):
        size, main = choose_sizes(each, own, target=target, floor=floor, reduced_sizes=2)
        assert got == pytest.approx(size, abs=0.01)
        assert points(found["main"]) == pytest.approx(main, abs=0.01)
    assert len({round(c, 2) for c in chosen}) == 3  # the main size, an upper group, and the floor
    assert chosen[-1] == pytest.approx(floor, abs=0.01)  # the absurd title is set at the floor
    warnings = [d.message for d in result.diagnostics if getattr(d, "code", "") == "TM-X019"]
    assert [w for w in warnings if "t8" in w and "does not fit" in w]  # and named, since there is no wrapping
    assert not [w for w in warnings if "settled" in w]


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_the_library_defines_what_it_declares(compiler):  # noqa: F811
    assert await check_library(compiler, pkg) == []
