"""Plans (B2, D2): lines with provenance, the baseline round trip, and edits by path."""

import pytest

from texmodel.components import Command, Environment, Value
from texmodel.document import Document
from texmodel.interface import Star, arg
from texmodel.package import Package
from texmodel.plan import Edit, EditKind, FieldEdit, Line, Plan, Span
from texmodel.preamble import PreambleSlots
from texmodel.types import Length, Raw, Text


def small():
    pkg = Package("small", prefix="sm")

    @pkg.command
    class Item(Command):
        """An item."""

        body = "#text"
        text: Text

    @pkg.environment
    class Box(Environment):
        """A box."""

        children = [Item.times.any()]
        begin = r"\begin{center}"
        end = r"\end{center}"

    return pkg, Item, Box


def test_every_line_has_the_path_of_what_wrote_it():
    pkg, item, box = small()
    plan = pkg.plan(
        Document(box(item(text="a"), item(text="b")), preamble=PreambleSlots(after_package=(Raw("\\x\n\\y"),)))
    )
    assert [(x.path, x.tex) for x in plan.lines] == [
        ("header", plan.lines[0].tex),
        ("document", r"\documentclass{article}"),
        ("document", r"\usepackage{small}"),
        ("preamble.after_package[0]", r"\x"),
        ("preamble.after_package[0]", r"\y"),
        ("document", r"\begin{document}"),
        ("Box[0]", r"\begin{smBox}"),
        ("Box[0]/Item[0]", r"  \smItem{a}"),
        ("Box[0]/Item[1]", r"  \smItem{b}"),
        ("Box[0]", r"\end{smBox}"),
        ("document", r"\end{document}"),
    ]
    assert plan.text == pkg.document(
        Document(box(item(text="a"), item(text="b")), preamble=PreambleSlots(after_package=(Raw("\\x\n\\y"),)))
    )
    assert plan.path_of(8) == "Box[0]/Item[0]"


def test_settings_have_a_path_too():
    pkg = Package("small", prefix="sm")

    @pkg.value
    class Gap(Value[Length]):
        """A gap."""

        default = Length("2mm")

    plan = pkg.plan(Document(settings=[Gap(Length("3mm"))]))
    assert [x.path for x in plan.lines if x.path.startswith("settings")] == ["settings[0]"]


def test_a_plan_round_trips_through_json():
    pkg, item, _ = small()
    plan = pkg.plan(item(text="é & ü"))
    assert Plan.from_json(plan.to_json()) == plan


def test_edits_name_changed_removed_and_added_lines():
    pkg, item, box = small()
    plan = pkg.plan(box(item(text="a"), item(text="b")))
    lines = plan.text.splitlines()
    changed = plan.text.replace(r"\smItem{a}", r"\smItem{A}")
    assert plan.edits(changed) == [
        Edit("Box[0]/Item[0]", r"  \smItem{a}", r"  \smItem{A}", EditKind.CHANGED, (FieldEdit("text", "A"),))
    ]
    assert plan.edits("\n".join(x for x in lines if "{b}" not in x)) == [
        Edit("Box[0]/Item[1]", r"  \smItem{b}", "", EditKind.REMOVED)
    ]
    assert plan.edits(plan.text.replace(r"\end{document}", "x\n\\end{document}")) == [
        Edit("Box[0]", "", "x", EditKind.ADDED)
    ]
    assert plan.edits(plan.text) == []


def test_an_invalid_document_has_no_plan():
    pkg, _, box = small()
    with pytest.raises(ExceptionGroup):
        pkg.plan(box(Length("1mm")))  # type: ignore[arg-type]


# --- argument spans and the field an edit changed ----------------------------------------------------------------


def spans_pkg():
    pkg = Package("spans", prefix="sp")

    @pkg.command
    class Note(Command):
        """A note."""

        text: Text
        label: Text | None = None
        body = "#label #text"

    @pkg.command
    class Head(Command):
        """A heading."""

        starred: Star = arg(default=False)
        text: Text
        body = "#starred #text"

    @pkg.command
    class Block(Command):
        """Raw TeX over lines."""

        tex: Raw
        body = "#tex"

    @pkg.environment
    class Panel(Environment):
        """A panel."""

        title: Text
        children = [Note.times.any()]
        begin = r"\begin{center}#title"
        end = r"\end{center}"

    return pkg, Note, Head, Block, Panel


def shown(line: Line) -> list[tuple[str, str]]:
    return [(s.arg, line.tex[s.start : s.end]) for s in line.spans]


def test_a_call_and_a_begin_line_have_spans_over_each_arguments_text():
    pkg, note, head, _, panel = spans_pkg()
    plan = pkg.plan(panel(note(text="n", label="L"), title="T"), head(text="H", starred=True))
    got = {x.tex: shown(x) for x in plan.lines if x.spans}
    assert got == {
        r"\begin{spPanel}{T}": [("title", "T")],
        r"  \spNote[L]{n}": [("label", "L"), ("text", "n")],
        r"\spHead*{H}": [("starred", "*"), ("text", "H")],
    }
    assert not any(x.spans for x in plan.lines if x.tex.startswith((r"\end", r"\documentclass")))


def test_a_call_over_several_lines_has_no_spans():
    pkg, _, _, block, _ = spans_pkg()
    plan = pkg.plan(block(tex=Raw("a\nb")))
    assert [x.spans for x in plan.lines if "Block" in x.path] == [(), ()]


def test_spans_round_trip_and_a_baseline_without_them_loads():
    pkg, note, _, _, _ = spans_pkg()
    plan = pkg.plan(note(text="n"))
    assert Plan.from_json(plan.to_json()) == plan
    assert Span("text", 8, 9) in next(x for x in plan.lines if x.path == "Note[0]").spans
    assert Plan.from_json('[["Note[0]", "\\\\spNote{n}"]]').lines == (Line("Note[0]", r"\spNote{n}"),)


@pytest.mark.parametrize(
    ("old", "new", "fields"),
    [
        (r"\spNote[L]{n}", r"\spNote[L]{m}", [("text", "m")]),
        (r"\spNote[L]{n}", r"\spNote[LL]{nn}", [("label", "LL"), ("text", "nn")]),
        (r"\spNote[L]{n}", r"\spNote[L]{}", [("text", "")]),  # the whole text deleted
        (r"\spNote[L]{n}", r"\spNote[L]{xn}", [("text", "xn")]),  # inserted at the start of an argument
        (r"\spNote[L]{n}", r"\spNote[L]{nx}", [("text", "nx")]),  # and at its end
        (r"\spHead*{H}", r"\spHead{H}", [("starred", "")]),  # a token removed at an edge
        (r"\spNote[L]{n}", r"\spNate[L]{n}", []),  # the command name
        (r"\spNote[L]{n}", r"\spNote(L){n}", []),  # a delimiter
        (r"\spNote[L]{n}", r"\spNote[L]{n}{extra}", []),  # outside every argument
        (r"\spNote[L]{n}", r"\spNote[L]x{n}", []),
    ],
)
def test_an_edit_names_the_argument_it_changed_only_when_the_change_is_inside_one(old, new, fields):
    pkg, note, head, _, _ = spans_pkg()
    plan = pkg.plan(note(text="n", label="L"), head(text="H", starred=True))
    text = plan.text.replace(old if old.startswith(r"\spNote") else r"\spHead*{H}", new, 1)
    (edit,) = plan.edits(text)
    assert [(f.arg, f.found) for f in edit.fields] == fields


def test_added_and_removed_lines_and_old_baselines_have_no_fields():
    pkg, note, _, _, _ = spans_pkg()
    plan = pkg.plan(note(text="n"))
    assert [e.fields for e in plan.edits(plan.text.replace(r"\spNote{n}", ""))] == [()]
    old = Plan(tuple(Line(x.path, x.tex) for x in plan.lines))  # a baseline saved without spans
    assert [e.fields for e in old.edits(plan.text.replace("{n}", "{m}"))] == [()]


def test_a_token_at_the_end_of_a_line_can_be_the_edited_argument():
    pkg = Package("spans", prefix="sp")

    @pkg.command
    class Tail(Command):
        """A call ending in a token."""

        text: Text
        starred: Star = arg(default=False)
        body = "#starred #text"

    plan = pkg.plan(Tail(text="t", starred=True))
    assert r"\spTail{t}*" in plan.text
    (edit,) = plan.edits(plan.text.replace(r"\spTail{t}*", r"\spTail{t}"))
    assert [(f.arg, f.found) for f in edit.fields] == [("starred", "")]
