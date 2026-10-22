import pathlib
from typing import Any

import pytest

from texmodel_build import diagnostics as d
from texmodel_build._internal.converge import aux_diff
from texmodel_build._internal.logparse import page_count, parse_log

LOGS = pathlib.Path(__file__).parent.parent / "fixtures" / "logs"


def kinds(name: str) -> list[Any]:  # Any: tests read the per-kind fields
    return list(parse_log((LOGS / name).read_text(encoding="utf-8", errors="replace")))


def test_a_clean_log_has_no_diagnostics_and_a_page_count():
    text = (LOGS / "ok.log").read_text(encoding="utf-8")
    assert parse_log(text) == ()
    assert page_count(text) == 1
    assert page_count("nothing") is None


def test_real_log_with_every_common_finding():
    found: dict[type, Any] = {type(x): x for x in kinds("diagnostics.log")}
    undefined = found[d.UndefinedControlSequence]
    assert (undefined.name, undefined.file, undefined.line) == ("\\undefinedmacro", "./bad.tex", 5)
    ref = found[d.UndefinedReference]
    assert (ref.kind, ref.name, ref.line, ref.severity) == ("Reference", "later", 6, d.Severity.WARNING)
    box = found[d.OverfullBox]
    assert (box.amount_pt, box.direction, box.line) == (114.97337, "h", 6)
    assert isinstance(found[d.RerunNeeded], d.RerunNeeded)


def test_missing_glyphs_are_errors_deduplicated_with_a_count():
    glyphs = [x for x in kinds("diagnostics.log") if isinstance(x, d.MissingCharacter)]
    assert {g.codepoint for g in glyphs} == {0x1D538, 0x16A0}
    assert all(g.severity is d.Severity.ERROR and g.count == 3 for g in glyphs)
    assert "TeX Gyre Termes" in glyphs[0].font


def test_missing_file_without_a_location_prefix_takes_its_line_from_the_context():
    (missing, *rest) = kinds("miss.log")
    assert isinstance(missing, d.MissingFile)
    assert (missing.name, missing.line, missing.file) == ("missingfile.tex", 3, None)
    assert rest == []  # "Emergency stop" and "Fatal error" are consequences, not findings
    assert kinds("sty.log")[0].name == "nonexistentpkg.sty"  # type: ignore[attr-defined]


def test_package_error_joins_its_continuation_lines():
    package = next(x for x in kinds("pkg.log") if isinstance(x, d.PackageError))
    assert package.package == "fontspec"
    assert 'The font "No Such Font Anywhere" cannot be found' in package.message
    assert package.count == 3
    assert any(isinstance(x, d.TexError) and "not loadable" in x.message for x in kinds("pkg.log"))


def test_probe_and_refusal_lines_and_unknown_overfull_location():
    out = parse_log(
        "texmodel:probe:fact.height=11.2mm\ntexmodel:refuse:too many facts\nOverfull \\vbox (3pt too high) x\n"
    )
    probe, refusal, box = out
    assert (probe.name, probe.value) == ("fact.height", "11.2mm")  # type: ignore[attr-defined]
    assert isinstance(refusal, d.DocumentRefusal) and refusal.message == "too many facts"
    assert isinstance(box, d.OverfullBox) and box.direction == "v" and box.line is None


@pytest.mark.parametrize(
    "line", ["LaTeX Warning: Label(s) may have changed. Rerun to get cross-references right.", "Please (re)run Biber"]
)
def test_rerun_phrasings(line):
    assert isinstance(parse_log(line)[0], d.RerunNeeded)


def test_undefined_control_sequence_without_context_still_reports():
    (u,) = parse_log("./a.tex:1: Undefined control sequence.\n")
    assert isinstance(u, d.UndefinedControlSequence) and u.name == ""


def test_every_kind_round_trips_through_a_dict():
    samples = [
        d.Diagnostic(),
        d.NotConverged(changed=("a", "b")),
        d.Unexplained(message="x"),
        d.MissingCharacter(font="f", codepoint=65, file="a.tex", line=2, count=4),
    ]
    for sample in samples:
        assert d.diagnostic_from_dict(sample.to_dict()) == sample
    wire = d.NotConverged(changed=("a",)).to_dict() | {"changed": ["a"]}  # JSON gives lists back
    assert d.diagnostic_from_dict(wire).changed == ("a",)  # type: ignore[attr-defined]


def test_aux_diff_names_the_labels_and_lines_that_moved():
    before = "\\newlabel{a}{{1}{1}}\n\\newlabel{b}{{2}{1}}\n\\@writefile{toc}{x}\n"
    after = "\\newlabel{a}{{1}{1}}\n\\newlabel{b}{{3}{1}}\n\\newlabel{c}{{1}{2}}\n"
    assert aux_diff(before, after) == ("\\@writefile{toc}{x}", "b", "c")
    assert aux_diff(before, before) == ()


def test_aux_diff_names_a_moving_macro_by_its_name():
    assert aux_diff("\\gdef\\run{1}\n", "\\gdef\\run{2}\n") == ("run",)


def test_a_package_warning_is_typed_with_its_continuation_lines_and_location():
    """A hand-written package's log: a card that does not fit is a package warning, not an overfull box (C2)."""
    (fit,) = kinds("overset.log")
    assert (fit.package, fit.line, fit.severity, fit.code) == ("card-deck", 36, d.Severity.WARNING, "TM-X019")
    assert fit.message == "Card 'Long-Eared Owl' does not fit. Its body needs 322.436pt and the card has 160.0pt"


def test_an_undefined_name_inside_an_argument_is_read_from_the_argument_line():
    """Real log: `\\setlength{\\cdSafeInset}` after a package removed the name; TeX shows it on `<argument>`."""
    (found,) = kinds("undefined_in_argument.log")
    assert isinstance(found, d.UndefinedControlSequence)
    assert (found.name, found.file, found.line) == ("\\cdSafeInset", "./deck.tex", 11)


# --- Measure (B2) ---------------------------------------------------------------------------------------------

FIT = d.Measure.declare(
    "fit",
    "card-deck",
    r"Card '(?P<item>[^']+)' does not fit\. Its body needs (?P<needs>\S+) and the card has (?P<has>\S+)",
)
OWL = {"item": "Long-Eared Owl", "needs_pt": 322.436, "has_pt": 160.0, "over_pt": 162.436}


def test_a_measure_rule_types_a_package_warning_and_keeps_the_warning():
    text = (LOGS / "overset.log").read_text(encoding="utf-8")
    warning, over = parse_log(text, [FIT])
    assert isinstance(warning, d.PackageWarning) and isinstance(over, d.Overset)
    assert (over.code, over.severity, over.line) == ("TM-X031", d.Severity.ERROR, 36)
    assert {k: getattr(over, k) for k in OWL} == OWL
    assert parse_log(text, [d.Measure.declare("other", "elsewhere", FIT.pattern.pattern)]) == (warning,)


def test_a_fit_probe_gives_the_same_overset_and_a_fitting_or_odd_one_gives_none():
    (probe, over) = parse_log("texmodel:probe:fit.Owl=322.436pt/160pt\n")
    assert isinstance(probe, d.Measurement) and isinstance(over, d.Overset)
    assert {k: getattr(over, k) for k in OWL if k != "item"} == {k: v for k, v in OWL.items() if k != "item"}
    assert (over.item, over.line) == ("Owl", None)  # a probe name has no spaces
    for value in ("1pt/2pt", "3", "x/y", "3pt/", "1pt/2pt/3pt"):
        assert [type(x) for x in parse_log(f"texmodel:probe:fit.a={value}\n")] == [d.Measurement]
    (_,) = parse_log("texmodel:probe:other=322pt/160pt\n")


def test_lengths_in_any_unit_are_read_in_points():
    assert d.points("25.4mm") == pytest.approx(72.27)
    assert d.points("1in") == pytest.approx(72.27) and d.points("5") == 5
    assert d.overset("a", "2cm", "10mm").over_pt == pytest.approx(28.452, abs=1e-3)  # type: ignore[union-attr]


@pytest.mark.parametrize("rule", [("(", "fit"), ("(?P<item>a)", "fit"), (FIT.pattern.pattern, "fill")])
def test_a_bad_measure_is_refused_when_it_is_declared(rule):
    from texmodel.errors import DeclarationError

    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-D032"):
        d.Measure.declare("m", "pk", *rule)
