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
