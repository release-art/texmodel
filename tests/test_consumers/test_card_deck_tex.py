"""Gate B, compiled: the synthetic deck through TeX, and what the compile reports for the defect classes."""

import pathlib
import re
import shutil

import pytest
from card_deck import convert, model
from test_texmodel_build.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.document import Document
from texmodel_build import diagnostics as d

pytestmark = [pytest.mark.tex, pytest.mark.timeout(300)]

OVERSET = re.compile(
    r"Card '(?P<name>.*)' does not fit\. Its body needs (?P<needs>[\d.]+)pt and the card has (?P<has>[\d.]+)pt"
)


def compile_deck(comp, tmp_path: pathlib.Path, tex: str, plan=None):
    src = tmp_path / "src"
    shutil.copytree(convert.HERE / "res", src / "res")
    (src / "deck.tex").write_text(tex, encoding="utf-8")
    return comp.compile(src / "deck.tex", tmp_path / "out", plan=plan)


def deck_of(*nodes) -> str:
    project = convert.load()[0]
    return model.pkg.document(Document(*nodes, settings=convert.settings(project), preamble=convert.preamble(project)))


def test_the_deck_compiles_to_one_page_per_card_face(compiler, tmp_path):  # noqa: F811
    result = compile_deck(compiler, tmp_path, convert.deck())
    assert result.ok and not [x for x in result.diagnostics if x.severity is d.Severity.ERROR]
    assert result.pages is not None and result.pages >= 3


def test_over_set_a_card_with_too_much_text_is_named_with_its_heights(compiler, tmp_path):  # noqa: F811
    """The package measures each back and warns per card; `OverfullBox` is not what it emits."""
    project, source = convert.load()
    long = {**source[1], "one_liners": [{**x, "text": (x["text"] + " ") * 8} for x in source[1]["one_liners"]]}
    nodes = (convert.card(1, source[0]), convert.card(2, long))
    plan = model.pkg.plan(Document(*nodes, settings=convert.settings(project), preamble=convert.preamble(project)))
    result = compile_deck(compiler, tmp_path, plan.text, plan)
    named = [m for x in result.diagnostics if isinstance(x, d.PackageWarning) and (m := OVERSET.search(x.message))]
    assert [m["name"] for m in named] == ["Long-Eared Owl"]
    assert float(named[0]["needs"]) > float(named[0]["has"])
    (warning,) = (x for x in result.diagnostics if isinstance(x, d.PackageWarning) and OVERSET.search(x.message))
    assert warning.path is not None and warning.path.startswith("Card[1]/")  # the compile names the card itself


def test_escaping_text_with_every_special_compiles_and_the_same_text_unescaped_does_not(compiler, tmp_path):  # noqa: F811
    text = "Call 999 or go to A&E: 30% of #1 _a_ ~b ^c $5 {d} \\e <f> “g” ‘h’ it’s — i"
    card = model.Card(
        model.CardFront(model.CardImage(path=model.Raw("images/special.jpg"))),
        model.CardBack(
            model.Name(text="R&D"),
            model.LeadFact(text=text),
            model.LeadFact(text="Two."),
            model.LabelledSlot(label=model.SlotLabel.SPOT, text=text),
        ),
    )
    tex = deck_of(card)
    ok = compile_deck(compiler, tmp_path / "escaped", tex)
    assert ok.ok and not any(isinstance(x, d.MissingCharacter) for x in ok.diagnostics)
    broken = compile_deck(compiler, tmp_path / "raw", tex.replace(r"A\&E", "A&E"))
    assert not broken.ok and any(x.severity is d.Severity.ERROR for x in broken.diagnostics)


def test_a_removed_name_is_an_undefined_control_sequence_a_compile_names(compiler, tmp_path):  # noqa: F811
    """The model refuses the same line before any compile (`TM-M015`); this is what TeX says instead."""
    stale = convert.deck().replace(r"\begin{document}", "\\setlength{\\cdSafeInset}{3mm}\n\\begin{document}")
    result = compile_deck(compiler, tmp_path, stale)
    assert [x.name for x in result.diagnostics if isinstance(x, d.UndefinedControlSequence)] == [r"\cdSafeInset"]
