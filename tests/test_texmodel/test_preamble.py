"""Typed preamble entries (§21a 10): rendered text, slot rules and plan paths."""

import pytest

from texmodel.package import Package, PreambleSlots
from texmodel.preamble import GraphicsPath, InputPath, PassOption, RequireMetadata
from texmodel.types import Raw


def test_entries_render_to_the_tex_a_hand_written_line_would_have():
    assert PassOption("xcolor", "table").raw() == Raw(r"\PassOptionsToPackage{table}{xcolor}")
    assert InputPath("res/", "more/").raw().tex == r"\makeatletter\def\input@path{{res/}{more/}}\makeatother"
    assert GraphicsPath("img/").raw().tex == r"\graphicspath{{}{img/}}"
    assert GraphicsPath("img/", include_cwd=False).raw().tex == r"\graphicspath{{img/}}"
    meta = RequireMetadata(lang="en-GB", pdfstandard="A-2b", pdftitle="A, B")
    assert meta.raw().tex == r"\DocumentMetadata{lang=en-GB, pdfstandard=A-2b, pdftitle={A, B}}"


def test_a_document_places_entries_and_names_them_by_path():
    pkg = Package("pre", prefix="pr", adopted=True)
    slots = PreambleSlots(
        before_class=(RequireMetadata(lang="en"),),
        before_package=(InputPath("res/"), Raw(r"\relax")),
        after_package=(GraphicsPath("img/"),),
    )
    plan = pkg.plan(preamble=slots)
    assert [(x.path, x.tex) for x in plan.lines if x.path.startswith("preamble")] == [
        ("preamble.before_class[0]", r"\DocumentMetadata{lang=en}"),
        ("preamble.before_package[0]", r"\makeatletter\def\input@path{{res/}}\makeatother"),
        ("preamble.before_package[1]", r"\relax"),
        ("preamble.after_package[0]", r"\graphicspath{{}{img/}}"),
    ]


def test_an_entry_in_the_wrong_slot_is_refused_with_its_path():
    pkg = Package("pre", prefix="pr", adopted=True)
    slots = PreambleSlots(
        before_class=(PassOption("a", "b"), GraphicsPath("x/")),
        before_package=(RequireMetadata(a="b"),),
        after_package=(InputPath("r/"), Raw(r"\anything")),
    )
    with pytest.raises(ExceptionGroup) as group:
        pkg.plan(preamble=slots)
    found = [(e.code, e.path) for e in group.value.exceptions]  # pyright: ignore[reportAttributeAccessIssue]
    assert found == [
        ("TM-C008", "preamble.before_class[1]"),
        ("TM-C008", "preamble.before_package[0]"),
        ("TM-C008", "preamble.after_package[0]"),
    ]
