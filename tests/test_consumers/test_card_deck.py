"""Gate B on a synthetic consumer: texmodel reproduces what a template generator printed, and catches what it missed.

The consumer (`tests/consumers/card_deck/`) mirrors a real deck's shape: a hand-written package, a generator that wrote
the `.tex`, and regex checks over that text. Its data is made up.
"""

import re
from typing import Any

import pytest
from card_deck import convert, legacy, model

from texmodel.package import PreambleSlots
from texmodel.plan import Plan
from texmodel.types import Raw, escape

STY = (convert.HERE / "res" / "card-deck.sty").read_text(encoding="utf-8")
OLD_STY = (convert.HERE / "old" / "card-deck.sty").read_text(encoding="utf-8")
PICTURE = re.compile(r"\\cdCardImage\{[^}]*\}")


def printed(tex: str) -> str:
    """What a `.tex` prints, to compare: no comments but the card audit blocks, one space, none inside braces, no
    picture lines, no `\\vspace` (a layout nudge the generator adds and the package's grammar does not carry)."""
    tex = re.sub(r"(?<!\\)%(?! Card: | {3}id: )[^\n]*", "", tex)
    tex = PICTURE.sub("", tex.replace(r"\vspace*{1mm}", ""))
    return re.sub(r" ?([{}]) ?", r"\1", re.sub(r"\s+", " ", tex)).strip()


def cards(tex: str) -> list[str]:
    head, *rest = printed(tex).split(r"\begin{cdCard}")
    return [head, *rest]


def test_the_model_prints_what_the_generator_printed_for_every_card():
    ours, theirs = cards(convert.deck()), cards(legacy.deck())
    assert len(ours) == len(theirs) == 4  # the preamble, then 3 cards
    assert ours[0] == theirs[0], "the preamble prints something else"
    assert [a == b for a, b in zip(ours[1:], theirs[1:], strict=True)] == [True] * 3


def test_the_audit_blocks_are_the_models_comment_nodes():
    audit = re.compile(r"^% Card: .*\n%   id: .*$", re.MULTILINE)
    assert len(audit.findall(convert.deck())) == 3
    assert audit.findall(convert.deck()) == audit.findall(legacy.deck())
    paths = [x.path for x in convert.plan().lines if x.tex.startswith("%") and "id: " in x.tex]
    assert paths == ["CardHeader[0]", "CardHeader[2]", "CardHeader[4]"]


def test_the_picture_paths_follow_the_generators_naming():
    theirs = [m.replace("{ ", "{").replace(" }", "}") for m in PICTURE.findall(legacy.deck())]
    assert PICTURE.findall(convert.deck()) == theirs


def test_the_title_is_set_in_title_case_by_a_deck_policy():
    assert r"\cdName{Long-Eared Owl}" in convert.deck()


def test_the_model_is_checked_against_the_package():
    assert model.pkg.check_interface(STY) == []


def test_a_hand_edited_slot_is_named_by_card_and_slot_without_reading_the_tex():
    plan = convert.plan()
    assert plan.edits(plan.text) == []
    (found,) = plan.edits(plan.text.replace("scream-like bark.", "scream-like bark (edited).", 1))
    assert found.path == "Card[1]/CardBack[1]/LabelledSlot[3]"
    assert found.expected.endswith("A loud, scream-like bark.}")
    assert found.found.endswith("scream-like bark (edited).}")


def test_a_removed_line_and_an_added_line_are_reported_too():
    plan = convert.plan()
    lines = plan.text.splitlines()
    dropped = next(i for i, ln in enumerate(lines) if r"\cdName{Garden Snail}" in ln)
    (gone,) = plan.edits("\n".join(lines[:dropped] + lines[dropped + 1 :]))
    assert (gone.path, gone.found) == ("Card[5]/CardBack[1]/Name[0]", "")
    (added,) = plan.edits(plan.text.replace(r"\end{document}", "stray\n" + r"\end{document}"))
    assert (added.expected, added.found) == ("", "stray")


def test_the_baseline_names_a_hand_edit_after_the_cards_have_moved_on(tmp_path):
    """The saved plan (not today's model) carries the paths: a card edited in `cards.toml` since the last compile
    does not misplace a hand edit made to the file."""
    baseline = tmp_path / "deck.tex.plan.json"
    baseline.write_text(convert.plan().to_json(), encoding="utf-8")
    project, source = convert.load()
    source[0]["one_liners"][0]["text"] = "Changed in the config."
    today = model.pkg.plan(
        *convert.body(source),
        settings=convert.settings(project),
        preamble=convert.preamble(project),
    )
    on_disk = convert.deck().replace("scream-like bark.", "scream-like bark (edited).", 1)
    saved = Plan.from_json(baseline.read_text(encoding="utf-8"))
    assert [e.path for e in saved.edits(on_disk)] == ["Card[1]/CardBack[1]/LabelledSlot[3]"]  # hand edit
    assert [e.path for e in saved.edits(today.text)] == ["Card[1]/CardBack[1]/LabelledSlot[4]"]  # config moved on


def test_known_gap_a_line_triaged_by_a_tool_reads_as_a_hand_edit():
    """A triage tool comments an over-set region out behind a marker, which the generator's regex drift code skips on
    purpose. The model's line diff has no such rule: it reports an edit."""
    plan, good = convert.plan(), convert.deck()
    mark = "%% (over-set: commented out to fit the card)"
    line = next(ln for ln in good.splitlines() if ln.startswith(r"\cdLabelledSlot{\deckParamFactWhere}"))
    (found,) = plan.edits(good.replace(line, f"{mark} {line}", 1))
    assert found.found.startswith(mark) and found.expected == line


# --- real defect classes --------------------------------------------------------------------------------------


def test_interface_drift_a_macros_arity_changed_in_the_package():
    (drifted,) = model.pkg.check_interface(OLD_STY)
    assert (drifted.code, drifted.path) == ("TM-C011", "TalkAboutMe")
    assert "declared [2][], the sources define [1]" in drifted.message


def test_interface_drift_is_what_texmodel_check_reports(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from texmodel import cli

    (tmp_path / "res").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[tool.texmodel]\npackage = "card_deck.model:pkg"\nsources = ["res/*.sty"]\n'
    )
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    (tmp_path / "res" / "card-deck.sty").write_text(OLD_STY)
    old = runner.invoke(cli.app, ["check"])
    assert old.exit_code == 1 and old.stdout.startswith("TM-C011 TalkAboutMe: ")
    (tmp_path / "res" / "card-deck.sty").write_text(STY)
    assert runner.invoke(cli.app, ["check"]).exit_code == 0


def test_interface_drift_a_deck_calls_a_name_the_package_removed():
    """The old package had `\\cdSafeInset`; a deck that kept using it stops with an undefined control sequence, found
    only at compile time. The model refuses the line first."""
    with pytest.raises(ExceptionGroup) as group:
        model.pkg.document(preamble=PreambleSlots(after_package=(Raw(r"\setlength{\cdSafeInset}{3mm}"),)))
    (error,) = group.value.exceptions
    assert (error.code, error.path) == ("TM-M015", "preamble.after_package[0]")  # pyright: ignore[reportAttributeAccessIssue]


def test_escaping_every_card_of_the_deck_agrees_with_the_generators_escape():
    _, source = convert.load()
    lines = [line["text"] for card in source for line in card["one_liners"]]
    assert any(c in "".join(lines) for c in "&%#_~’")
    assert all(escape(convert.text(t)) == legacy.latex_escape(t) for t in lines)


def test_escaping_where_texmodel_and_the_generator_differ():
    """The generator escapes `<` `>` and prints `^` as an accent on nothing; texmodel leaves the angle brackets and
    uses `\\textasciicircum`. A typographic apostrophe passes through untouched."""
    assert (escape("a<b>c"), legacy.latex_escape("a<b>c")) == ("a<b>c", r"a\textless{}b\textgreater{}c")
    assert (escape("x^2"), legacy.latex_escape("x^2")) == (r"x\textasciicircum{}2", r"x\^{}2")
    assert (escape("it’s"), legacy.latex_escape("it’s")) == ("it’s", "it's")


def test_a_picture_path_is_raw_because_escaping_it_would_break_the_file_name():
    assert model.CardImage(Raw("images/a_b.jpg")).render() == r"\cdCardImage{images/a_b.jpg}"
    assert escape("images/a_b.jpg") == r"images/a\_b.jpg"


def test_the_cards_round_trip_through_data_and_the_schema_covers_the_grammar():
    from texmodel.spec import from_dict, json_schema, to_dict

    for card in convert.nodes():
        assert from_dict(model.Card, to_dict(card)) == card
    header = model.CardHeader("Red Fox", "1")
    inside = model.Card(header, *convert.nodes()[0].content)
    assert from_dict(model.Card, to_dict(inside)) == inside
    schema = json_schema(model.Card)
    assert set(schema["$defs"]) >= {"CardFront", "CardBack", "LabelledSlot", "TalkAboutMe", "CardHeader", "Comment"}
    assert schema["$defs"]["TalkAboutMe"]["required"] == ["question"]


def test_the_package_schema_accepts_what_to_dict_writes_for_every_card_and_refuses_a_wrong_child():
    import jsonschema

    from texmodel.spec import json_schema, to_dict

    schema = json_schema(model.pkg) | {"$ref": "#/$defs/Card"}
    validator = jsonschema.Draft202012Validator(schema)
    jsonschema.Draft202012Validator.check_schema(schema)
    for card in convert.nodes():
        assert validator.is_valid(dict[str, Any](to_dict(card)))
    data = dict[str, Any](to_dict(model.Card(model.CardHeader("Fox", "1"), *convert.nodes()[0].content)))
    assert validator.is_valid(data)
    data["content"] = [{"type": "LabelledSlot", "text": "x"}]  # a child the grammar does not list
    assert not validator.is_valid(data)
