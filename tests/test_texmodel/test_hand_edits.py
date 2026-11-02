"""Hand edits read from the calls a document writes: the merge of the calls with the lines."""

import pathlib

import pytest

from texmodel._internal.calls import ParsedCall, parse_calls
from texmodel.body import RefKind
from texmodel.components import Command, Environment, Passthrough, control_name
from texmodel.document import Document
from texmodel.errors import TexmodelError
from texmodel.hand_edits import read_edits
from texmodel.package import Package
from texmodel.plan import BEGIN_DOCUMENT, EditKind
from texmodel.std import tabularray as t
from texmodel.types import Length, Raw, Text

pkg = Package("hands", prefix="hd")


@pkg.command
class Para(Command):
    """A paragraph."""

    text: Text
    body = r"\par #text\par"


@pkg.command
class Note(Command):
    """A note."""

    text: Text
    label: Text | None = None
    body = r"\par [#label] #text\par"


@pkg.command
class Meter(Command):
    """Scalars."""

    width: Length
    count: int
    ratio: float
    body = r"\par #width #count #ratio\par"


@pkg.environment
class Inner(Environment):
    """A box."""

    title: Text
    children = [Para.times.any(), Note.times.any(), Passthrough.times.any()]
    begin = r"\begin{center}#title"
    end = r"\end{center}"


NODES = (
    Inner(Para(text="a"), Para(text="a"), Note(text="n", label="L"), title="T"),
    Meter(width=Length("3cm"), count=3, ratio=0.5),
    Para(text="z"),
)
PLAN = pkg.plan(*NODES)


def read(edited: str):
    return read_edits(PLAN, edited, pkg)


def kinds(edited: str) -> list[tuple[str, EditKind]]:
    return [(e.path, e.kind) for e in read(edited)]


def test_the_argument_that_changed_is_named_with_its_typed_value():
    edited = PLAN.text.replace(r"\hdNote[L]{n}", r"\hdNote[LL]{n}")
    (edit,) = read(edited)
    assert (edit.path, edit.kind) == ("Inner[0]/Note[2]", EditKind.CHANGED)
    assert [(f.arg, f.found, f.value) for f in edit.fields] == [("label", "LL", "LL")]
    assert edit.expected == r"  \hdNote[L]{n}" and edit.found == r"  \hdNote[LL]{n}"


def test_an_escaped_value_is_read_as_the_text_it_writes():
    (edit,) = read(PLAN.text.replace(r"\hdNote[L]{n}", r"\hdNote[L]{R\& D}"))
    assert [(f.arg, f.value) for f in edit.fields] == [("text", "R& D")]


def test_a_value_that_is_not_of_the_type_carries_a_violation_at_the_field():
    (edit,) = read(PLAN.text.replace("{3}", "{three}"))
    (field,) = edit.fields
    assert field.value is None and field.violation and field.violation.path == "Meter[1].count"
    assert field.violation.code == "TM-C021"


def test_a_line_that_differs_but_reads_the_same_is_unread():
    assert kinds(PLAN.text.replace(r"\hdPara{z}", r"\hdPara{z} % why")) == [("Para[2]", EditKind.UNREAD)]


def test_text_that_reads_as_the_same_value_is_unread():
    (edit,) = read(PLAN.text.replace("{0.5}", "{.5}"))
    assert edit.kind is EditKind.UNREAD and edit.fields == ()


def test_a_call_that_cannot_be_read_is_unread_and_an_added_one_is_added():
    assert kinds(PLAN.text.replace(r"\hdPara{z}", r"\hdPara{z")) == [("Para[2]", EditKind.UNREAD)]
    assert kinds(PLAN.text.replace(r"\hdPara{z}", "\\hdPara{z}\n\\hdPara{open")) == [("Para[2]", EditKind.ADDED)]


def test_a_removed_call_is_removed_once():
    assert kinds(PLAN.text.replace("\\hdPara{z}\n", "")) == [("Para[2]", EditKind.REMOVED)]


def test_an_added_call_belongs_to_the_call_before_it():
    edited = PLAN.text.replace("\\hdPara{z}\n", "\\hdPara{z}\n\\hdPara{y}\n")
    assert kinds(edited) == [("Para[2]", EditKind.ADDED)]


def test_every_edit_carries_the_file_and_a_line_edit_its_line():
    edited = PLAN.text.replace(r"\begin{hdInner}{T}", r"\begin{hdInner}{TT}")
    deck = pathlib.Path("decks/a.tex")
    (changed,) = read_edits(PLAN, edited, pkg, file=deck)
    assert (changed.file, changed.line) == (deck, edited.splitlines().index(r"\begin{hdInner}{TT}") + 1)
    assert changed.plan_line == next(i for i, x in enumerate(PLAN.lines, 1) if x.tex == r"\begin{hdInner}{T}")


def test_a_call_added_before_every_other_follows_begin_document():
    first = next(i for i, x in enumerate(PLAN.lines) if x.path.startswith("Inner"))
    edited = (
        "\n".join([*(x.tex for x in PLAN.lines[:first]), r"\hdPara{y}", *(x.tex for x in PLAN.lines[first:])]) + "\n"
    )
    (edit,) = read(edited)
    assert (edit.kind, edit.plan_line) == (EditKind.ADDED, PLAN.lines.index(BEGIN_DOCUMENT) + 1)


def test_equal_calls_are_named_once_though_the_two_diffs_name_different_ones():
    assert [k for _, k in kinds(PLAN.text.replace("  \\hdPara{a}\n", "", 1))] == [EditKind.REMOVED]


def test_a_call_tex_does_not_run_is_removed_though_its_line_is_there():
    got = kinds(PLAN.text.replace("\\hdPara{z}\n", "\\iffalse\n\\hdPara{z}\n\\fi\n"))
    assert got.count(("Para[2]", EditKind.REMOVED)) == 1
    assert [k for _, k in got].count(EditKind.ADDED) == 2


def test_a_call_commented_out_is_one_removal_of_its_line():
    (edit,) = read(PLAN.text.replace("\\hdPara{z}\n", "% \\hdPara{z}\n"))
    assert (edit.path, edit.kind, edit.found) == ("Para[2]", EditKind.REMOVED, "% \\hdPara{z}")


def test_another_command_on_the_line_is_a_change_without_fields():
    (edit,) = read(PLAN.text.replace(r"\hdPara{z}", r"\hdNote{z}"))
    assert (edit.kind, edit.fields, edit.found) == (EditKind.CHANGED, (), r"\hdNote{z}")


def test_an_environments_title_is_read():
    (edit,) = read(PLAN.text.replace("{T}", "{TT}"))
    assert (edit.path, [f.arg for f in edit.fields]) == ("Inner[0]", ["title"])


def test_the_plan_reads_as_the_calls_its_nodes_make():
    classes = {control_name(c): c for c in (Para, Note, Meter, Inner)}
    made = [p for p in parse_calls(PLAN.text, classes) if isinstance(p, ParsedCall)]
    assert [(p.call.kind, p.call.name) for p in made][:2] == [(RefKind.OPEN, "hdInner"), (RefKind.CALL, "hdPara")]
    assert read(PLAN.text) == []


def test_no_package_means_nothing_to_read():
    with pytest.raises(TexmodelError) as raised:
        read_edits(PLAN, PLAN.text)
    assert raised.value.code == "TM-X033"


rows_pkg = Package("hand-rows", prefix="hr")


@rows_pkg.command
class Entry(t.TableRow):
    """A row of two cells."""

    key: Text
    value: Text


def entries() -> t.Tblr:
    rows = [Entry(key="a", value="1"), Entry(key="b", value="2")]
    return t.Tblr(*rows, outer=t.TblrOuter(expand=t.expand_of(rows)), inner=t.TblrInner(colspec=Raw("QQ")))


def test_a_table_is_read_whenever_a_row_is():
    plan = rows_pkg.plan(Document(entries()))
    (edit,) = read_edits(plan, plan.text.replace("{2}", "{two}"), rows_pkg)
    assert (edit.path, edit.kind) == ("Tblr[0]/Entry[1]", EditKind.CHANGED)
    assert [(f.arg, f.value) for f in edit.fields] == [("value", "two")]
    (begin,) = read_edits(plan, plan.text.replace("QQ", "QQQ"), rows_pkg)
    assert (begin.path, begin.kind) == ("Tblr[0]", EditKind.CHANGED) and begin.fields


def test_stub_adds_components_of_other_packages():
    (edit,) = read_edits(PLAN, PLAN.text.replace(r"\hdPara{z}", r"\hrEntry{z}{y}"), pkg, stub=[Entry])
    assert edit.kind is EditKind.CHANGED and edit.fields == ()


def test_a_plan_with_a_call_inside_a_definition_is_refused():
    plan = pkg.plan(Passthrough(Raw(r"\newcommand{\x}[1]{\hdPara{#1}}")), Passthrough(Raw(r"\x{one}")))
    with pytest.raises(TexmodelError) as raised:
        read_edits(plan, plan.text, pkg)
    assert raised.value.code == "TM-X035" and "line 5" in str(raised.value)


def test_a_call_a_hand_edit_wraps_in_a_macro_is_unread_not_misread():
    edited = PLAN.text.replace(r"\hdPara{z}", "\\newcommand{\\y}[1]{\\hdPara{#1}}\n\\y{zz}")
    got = [(e.path, e.kind, e.fields) for e in read(edited)]
    assert got == [("Para[2]", EditKind.UNREAD, ()), ("Para[2]", EditKind.ADDED, ())]
