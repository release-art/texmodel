"""Plans (B2, D2): lines with provenance, the baseline round trip, and edits by path."""

import pytest

from texmodel.components import Command, Environment, Value
from texmodel.package import Package, PreambleSlots
from texmodel.plan import Edit, Plan
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
    plan = pkg.plan(box(item("a"), item("b")), preamble=PreambleSlots(after_package=(Raw("\\x\n\\y"),)))
    assert [(x.path, x.tex) for x in plan.lines] == [
        ("header", plan.lines[0].tex),
        ("document", r"\documentclass{article}"),
        ("document", r"\usepackage{small}"),
        ("preamble.after_package[0]", r"\x"),
        ("preamble.after_package[0]", r"\y"),
        ("document", r"\begin{document}"),
        ("Box[0]", r"\begin{smBox}"),
        ("Box[0]/Item[0]", r"\smItem{a}"),
        ("Box[0]/Item[1]", r"\smItem{b}"),
        ("Box[0]", r"\end{smBox}"),
        ("document", r"\end{document}"),
    ]
    assert plan.text == pkg.document(
        box(item("a"), item("b")), preamble=PreambleSlots(after_package=(Raw("\\x\n\\y"),))
    )
    assert plan.path_of(8) == "Box[0]/Item[0]"


def test_settings_have_a_path_too():
    pkg = Package("small", prefix="sm")

    @pkg.value
    class Gap(Value[Length]):
        """A gap."""

        default = Length("2mm")

    plan = pkg.plan(settings=[Gap(Length("3mm"))])
    assert [x.path for x in plan.lines if x.path.startswith("settings")] == ["settings[0]"]


def test_a_plan_round_trips_through_json():
    pkg, item, _ = small()
    plan = pkg.plan(item("é & ü"))
    assert Plan.from_json(plan.to_json()) == plan


def test_edits_name_changed_removed_and_added_lines():
    pkg, item, box = small()
    plan = pkg.plan(box(item("a"), item("b")))
    lines = plan.text.splitlines()
    changed = plan.text.replace(r"\smItem{a}", r"\smItem{A}")
    assert plan.edits(changed) == [Edit("Box[0]/Item[0]", r"\smItem{a}", r"\smItem{A}")]
    assert plan.edits("\n".join(x for x in lines if "{b}" not in x)) == [Edit("Box[0]/Item[1]", r"\smItem{b}", "")]
    assert plan.edits(plan.text.replace(r"\end{document}", "x\n\\end{document}")) == [Edit("Box[0]", "", "x")]
    assert plan.edits(plan.text) == []


def test_an_invalid_document_has_no_plan():
    pkg, _, box = small()
    with pytest.raises(ExceptionGroup):
        pkg.plan(box(Length("1mm")))  # type: ignore[arg-type]
