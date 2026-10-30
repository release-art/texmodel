"""Restoring the data behind a hand-edited document (§21), on the synthetic card deck: what restores, what comes
back unapplied with its reason, and the law that the restored data writes every edit it holds."""

import dataclasses
import pathlib
import re
import string
from typing import Any

import pytest
from card_deck import convert, model
from hypothesis import (
    given,
    settings,
    strategies as st,
)
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

import texmodel
from texmodel.components import Command
from texmodel.document import Document
from texmodel.errors import DeclarationError, Violation
from texmodel.package import Package
from texmodel.plan import Edit, EditKind, FieldEdit, data_path
from texmodel.restore import Reason, restore
from texmodel.run.hand_edits import read_edits
from texmodel.spec import to_dict
from texmodel.types import CMYK, Text, escape

PROJECT, CARDS = convert.load()
DECK = Document(*convert.body(CARDS), settings=convert.settings(PROJECT), preamble=convert.preamble(PROJECT))
PLAN = model.pkg.plan(DECK)
TEXT = PLAN.text
FOX_FACT = r"    \cdLeadFact{Its whiskers help it feel in the dark.}"
FOX_WHERE = r"    \cdLabelledSlot{\deckParamFactWhere}{In gardens and parks.}"
OWL_FACT = r"    \cdLeadFact{Owls swallow small prey whole.}"


def data(document: Document) -> Any:  # noqa: ANN401  # to_dict's nested data, indexed in the asserts
    return to_dict(document)


def restored(text: str):
    return restore(model.pkg, DECK, PLAN.edits(text))


def reasons(text: str) -> list[tuple[str, Reason]]:
    return [(u.edit.path, u.reason) for u in restored(text).unapplied]


def test_a_reworded_fact_restores_as_its_new_text_and_writes_the_edited_file():
    edited = TEXT.replace(FOX_FACT, r"    \cdLeadFact{Its whiskers feel 50\% of the dark.}")
    found = restored(edited)
    assert [e.path for e in found.applied] == ["Card[1]/CardBack[1]/LeadFact[2]"] and found.unapplied == ()
    assert model.pkg.plan(found.document).text == edited
    back = data(found.document)["content"][1]["content"][1]["content"][2]
    assert back == {"type": "LeadFact", "text": "Its whiskers feel 50% of the dark."}
    assert found.applied[0].data_path == pathlib.PurePosixPath("/content/1/content/1/content/2")


@pytest.mark.parametrize(
    "line",
    ["", f"%{FOX_WHERE}", f"    % {FOX_WHERE.lstrip()}", f"%   {FOX_WHERE}"],
    ids=["deleted", "commented-at-the-margin", "commented-after-the-indent", "commented-with-spaces"],
)
def test_a_dropped_slot_deleted_or_commented_out_is_removed_from_its_card(line):
    edited = TEXT.replace(FOX_WHERE + "\n", line + "\n" if line else "")
    found = restored(edited)
    assert [e.path for e in found.applied] == ["Card[1]/CardBack[1]/LabelledSlot[5]"] and found.unapplied == ()
    back = data(found.document)["content"][1]["content"][1]["content"]
    assert [c["type"] for c in back][-1] == "LabelledSlot" and len(back) == 5
    assert model.pkg.plan(found.document).text == TEXT.replace(FOX_WHERE + "\n", "")  # regeneration writes no line


def test_a_removed_card_restores_as_removed_and_its_id_stays():
    lines = TEXT.splitlines()
    card = [i for i, x in enumerate(PLAN.lines) if x.path == "Card[3]" or x.path.startswith("Card[3]/")]
    edited = "\n".join(x for i, x in enumerate(lines) if i not in card) + "\n"
    found = restored(edited)
    assert {e.path.split("/")[0] for e in found.applied} == {"Card[3]"} and found.unapplied == ()
    assert [type(n).__name__ for n in found.document.content] == [
        "CardHeader",
        "Card",
        "CardHeader",
        "CardHeader",
        "Card",
    ]


def test_a_removal_the_grammar_refuses_comes_back_with_its_rule():
    (refused,) = restored(TEXT.replace(OWL_FACT + "\n", "")).unapplied
    assert (refused.edit.path, refused.reason) == ("Card[3]/CardBack[1]/LeadFact[2]", Reason.GRAMMAR)
    assert refused.violation is not None and refused.violation.code == "TM-C002"


@pytest.mark.parametrize(
    ("old", "new", "reason"),
    [
        (FOX_FACT, FOX_FACT.replace("LeadFact", "LeadFacts"), Reason.NOT_IN_ARGUMENT),
        (FOX_FACT, f"% {FOX_FACT.lstrip().replace('dark', 'night')}", Reason.PARTIAL_REMOVAL),  # commented and edited
        (FOX_FACT, f"%%{FOX_FACT}", Reason.PARTIAL_REMOVAL),
        (r"\cdName{Red Fox}", r"\cdName{R&D Fox}", Reason.INVALID_VALUE),  # an unescaped special: no Text value
        (FOX_FACT, FOX_FACT.replace("help it", "help  it"), Reason.MISMATCH),  # TeX reads one space; it writes one
        ("%   id: 11111111-aaaa", "%   id: 99999999-zzzz", Reason.COMMENT),
        ("% Card: Red Fox\n%   id: 11111111-aaaa\n", "", Reason.COMMENT),
        ("% Card: Red Fox", "% % Card: Red Fox", Reason.COMMENT),
        (r"\renewcommand{\cdDeckName}{Garden Animals}", r"\renewcommand{\cdDeckName}{Garden}", Reason.SETTING),
        (r"\def\deckBeforeClass{yes}", r"\def\deckBeforeClass{no}", Reason.NOT_DATA),
        (r"\documentclass{article}", r"\documentclass[a5paper]{article}", Reason.NOT_DATA),
        (FOX_FACT, FOX_FACT + "\n    \\cdLeadFact{A third fact.}", Reason.ADDED_LINE),
    ],
)
def test_an_edit_that_is_not_restored_comes_back_with_its_reason(old, new, reason):
    assert TEXT.count(old) == 1
    found = restored(TEXT.replace(old, new))
    assert found.unapplied and {u.reason for u in found.unapplied} == {reason} and found.applied == ()
    assert found.document == DECK


def test_part_of_a_node_removed_is_a_partial_removal():
    end = next(i for i, x in enumerate(PLAN.lines) if x.path == "Card[1]/CardBack[1]" and "end" in x.tex)
    edited = "\n".join(x.tex for i, x in enumerate(PLAN.lines) if i != end) + "\n"
    assert reasons(edited) == [("Card[1]/CardBack[1]", Reason.PARTIAL_REMOVAL)]


CARD_BACK = "  \\begin{cdCardBack}"


@pytest.mark.parametrize(
    ("before", "parent", "after"),
    [
        (FOX_FACT, "Card[1]/CardBack[1]", "Card[1]/CardBack[1]/LeadFact[2]"),  # among the children
        (CARD_BACK, "Card[1]/CardBack[1]", None),  # right after a \begin: the first child
        ("\\end{cdCard}", "", "Card[1]"),  # after a card: at the top level
        ("\\begin{document}", "", None),
        ("%   id: 11111111-aaaa", "", "CardHeader[0]"),
        ("\\documentclass{article}", None, None),  # outside the content
        ("\\def\\deckBeforeClass{yes}", None, None),  # after a preamble entry
    ],
)
def test_an_added_line_says_the_node_it_stands_in_and_the_child_it_follows(before, parent, after):
    edited = TEXT.replace(before + "\n", before + "\n    \\cdLeadFact{New.}\n", 1)
    (added,) = restored(edited).unapplied
    assert (added.reason, added.parent, added.after) == (Reason.ADDED_LINE, parent, after)


def test_a_line_added_before_every_line_is_outside_the_content():
    (added,) = restored("% a note\n" + TEXT).unapplied
    assert (added.reason, added.parent, added.after) == (Reason.ADDED_LINE, None, None)


def test_a_mismatch_says_what_the_restored_data_writes():
    (mismatch,) = restored(TEXT.replace(FOX_FACT, FOX_FACT.replace("help it", "help  it"))).unapplied
    assert mismatch.writes == FOX_FACT


def test_one_edit_that_does_not_restore_holds_back_no_other():
    edited = TEXT.replace(FOX_FACT, FOX_FACT.replace("dark", "night")).replace(r"{Red Fox}", r"{R&D Fox}")
    found = restored(edited)
    assert [e.path for e in found.applied] == ["Card[1]/CardBack[1]/LeadFact[2]"]
    assert reasons(edited) == [("Card[1]/CardBack[1]/Name[0]", Reason.INVALID_VALUE)]


def test_unread_edits_have_no_data_change_and_every_edit_comes_back_in_the_order_given():
    n = next(i for i, x in enumerate(PLAN.lines, 1) if x.tex == FOX_WHERE)
    unread = Edit(PLAN.lines[n - 1].path, FOX_WHERE, FOX_WHERE + " % a note", EditKind.UNREAD, plan_line=n)
    changed = PLAN.edits(TEXT.replace(FOX_FACT, FOX_FACT.replace("dark", "night")))
    found = restore(model.pkg, DECK, [unread, *changed])
    assert [u.reason for u in found.unapplied] == [Reason.NO_DATA_CHANGE] and list(found.applied) == changed


def test_a_value_read_by_tex_that_failed_comes_back_with_its_violation():
    (edit,) = PLAN.edits(TEXT.replace(FOX_FACT, FOX_FACT.replace("dark", "night")))
    bad = dataclasses.replace(edit.fields[0], violation=Violation("TM-C021", "text", "text: read by TeX, refused"))
    (back,) = restore(model.pkg, DECK, [dataclasses.replace(edit, fields=(bad,))]).unapplied
    assert back.reason is Reason.INVALID_VALUE and back.violation is bad.violation


def test_edits_of_another_document_are_refused():
    (name,) = PLAN.edits(TEXT.replace(r"\cdName{Red Fox}", r"\cdName{Fox}"))
    other = dataclasses.replace(name, expected=r"    \cdName{Grey Fox}")  # another document wrote another line there
    unplaced = dataclasses.replace(name, plan_line=None)  # not found against a plan
    added = Edit("Card[9]", "", r"\cdName{Fox}", EditKind.ADDED, plan_line=3)
    for edit in (other, unplaced, added, dataclasses.replace(name, plan_line=len(PLAN.lines) + 1)):
        with pytest.raises(DeclarationError) as raised:
            restore(model.pkg, DECK, [edit])
        assert raised.value.code == "TM-X034"


# --- a field restore cannot read, and an optional left out ------------------------------------------------------------

small = Package("restore-small", prefix="rs")


@small.command
class Swatch(Command):
    """A colour, which its text does not say the model of."""

    ink: CMYK
    body = r"\color{#ink}"


@small.command
class Note(Command):
    """A note with an optional label."""

    text: Text
    label: Text | None = None
    body = r"[#label] #text"


def test_a_field_whose_type_is_not_read_back_from_text_is_unreadable():
    document = Document(Swatch(ink=CMYK(0, 0, 0, 1)))
    plan = small.plan(document)
    (edit,) = plan.edits(plan.text.replace("0,0,0,1", "0,0,0,0.5"))
    (back,) = restore(small, document, [edit]).unapplied
    assert back.reason is Reason.UNREADABLE


def test_an_optional_argument_left_out_restores_as_its_default():
    document = Document(Note(text="n", label="L"))
    plan = small.plan(document)
    n = next(i for i, x in enumerate(plan.lines, 1) if x.path == "Note[0]")
    plain = Note(text="n").render()
    # as `read_edits` reports it: TeX sees the optional argument empty
    edit = Edit("Note[0]", plan.lines[n - 1].tex, plain, EditKind.CHANGED, (FieldEdit("label", ""),), plan_line=n)
    found = restore(small, document, [edit])
    assert found.applied == (edit,) and data(found.document)["content"][0] == {
        "type": "Note",
        "text": "n",
        "label": None,
    }


# --- the registry, the paths, the law -------------------------------------------------------------------------------


def test_reasons_are_one_registry_and_no_other_module_writes_their_codes():
    src = pathlib.Path(texmodel.__file__).parent
    found = sorted(str(p.relative_to(src)) for p in src.rglob("*.py") if re.search(r"TM-R\d", p.read_text("utf-8")))
    assert found == ["restore.py"] and len({r.value for r in Reason}) == len(Reason)


def test_a_plan_path_has_the_data_path_of_its_writer():
    assert data_path("Card[1]/CardBack[1]/Name[0]") == pathlib.PurePosixPath("/content/1/content/1/content/0")
    assert data_path("settings[2]") == pathlib.PurePosixPath("/settings/2")
    assert data_path("preamble.after_package[0]") == pathlib.PurePosixPath("/preamble/after_package/0")
    assert data_path("header") is None and data_path("document") is None
    assert data_path("") == pathlib.PurePosixPath("/")  # the document: the parent of its top-level nodes


WORDS = st.text(alphabet=string.ascii_letters + string.digits + "&%$#_.,'", min_size=1, max_size=8)
TEXTS = st.lists(WORDS, min_size=1, max_size=5).map(" ".join)
CALL = re.compile(r"^(\s*\\cd(?:Name|LeadFact)\{)(.*)(\})$")
DROPPABLE = [i for i, x in enumerate(PLAN.lines) if re.search(r"LabelledSlot\[\d\]$", x.path)]


@settings(max_examples=40, deadline=None)
@given(
    st.dictionaries(st.sampled_from([i for i, x in enumerate(PLAN.lines) if CALL.match(x.tex)]), TEXTS, max_size=4),
    st.dictionaries(st.sampled_from(DROPPABLE), st.booleans(), max_size=3),
)
def test_the_restored_data_writes_every_edit_it_holds(reworded, dropped):
    """The law: rewordings (escaped as texmodel escapes) and dropped slots (deleted, or commented out) all restore, and
    the restored document writes the edited file, but for the commented lines, which regeneration does not write."""
    lines: list[str | None] = [x.tex for x in PLAN.lines]
    for i, words in reworded.items():
        m = CALL.match(PLAN.lines[i].tex)
        lines[i] = f"{m[1]}{escape(words)}{m[3]}" if m else lines[i]
    for i, comment in dropped.items():
        lines[i] = f"%{lines[i]}" if comment else None
    edited = "\n".join(x for x in lines if x is not None) + "\n"
    found = restored(edited)
    assert found.unapplied == ()
    written = "\n".join(x for i, x in enumerate(lines) if x is not None and i not in dropped) + "\n"
    assert model.pkg.plan(found.document).text == written


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_edits_read_by_tex_restore_as_the_lines_do(compiler):  # noqa: F811
    edited = TEXT.replace(FOX_FACT, FOX_FACT.replace("dark", "night")).replace(FOX_WHERE, f"% {FOX_WHERE.lstrip()}")
    files = {"res/card-deck.sty": (convert.HERE / "res" / "card-deck.sty").read_text(encoding="utf-8")}
    by_tex = restore(model.pkg, DECK, await read_edits(compiler, PLAN, edited, model.pkg, files=files))
    by_lines = restored(edited)
    assert by_tex.document == by_lines.document != DECK and len(by_tex.applied) == 2 and by_tex.unapplied == ()
