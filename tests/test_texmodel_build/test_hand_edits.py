"""Hand edits read by TeX (hand-edit-probe-spec): the merge of calls and lines without TeX, and one compile."""

import re
import typing

import pytest

from test_texmodel_build.test_compile_tex import compiler, fonts  # noqa: F401
from texmodel.body import RefKind
from texmodel.components import Command, Environment, Passthrough
from texmodel.errors import TexmodelError
from texmodel.package import Package
from texmodel.plan import EditKind
from texmodel.testing import Call, expand
from texmodel.types import Length, Text
from texmodel_build import hand_edits
from texmodel_build.compiler import Compiler
from texmodel_build.hand_edits import read_edits

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


STUBS = [Para, Note, Meter, Inner]
NODES = (Inner(Para("a"), Para("a"), Note("n", label="L"), title="T"), Meter(Length("3cm"), 3, 0.5), Para("z"))
PLAN = pkg.plan(*NODES)
BASE = [c for n in NODES for c in expand(n, STUBS) if isinstance(c, Call)]
NO_COMPILER = typing.cast("Compiler", None)


def read(monkeypatch: pytest.MonkeyPatch, edited: str, calls: list[Call]):
    answers = iter([BASE, calls])  # the plan's own text first, then the edited one
    monkeypatch.setattr(hand_edits, "_calls", lambda *_: next(answers))
    return read_edits(NO_COMPILER, PLAN, edited, pkg)


def without(calls: list[Call], *indexes: int) -> list[Call]:
    return [c for i, c in enumerate(calls) if i not in indexes]


def with_args(calls: list[Call], index: int, *args: str) -> list[Call]:
    return [Call(c.name, args, c.kind) if i == index else c for i, c in enumerate(calls)]


def test_the_probe_names_the_argument_with_its_typed_value(monkeypatch):
    edited = PLAN.text.replace(r"\hdNote[L]{n}", r"\hdNote[LL]{n}")
    (edit,) = read(monkeypatch, edited, with_args(BASE, 3, "LL", "n"))
    assert (edit.path, edit.kind) == ("Inner[0]/Note[2]", EditKind.CHANGED)
    assert [(f.arg, f.found, f.value) for f in edit.fields] == [("label", "LL", "LL")]
    assert edit.expected == r"\hdNote[L]{n}" and edit.found == r"\hdNote[LL]{n}"


def test_a_value_that_is_not_of_the_type_carries_a_violation_at_the_field(monkeypatch):
    edited = PLAN.text.replace("{3}", "{three}")
    (edit,) = read(monkeypatch, edited, with_args(BASE, 5, "3cm", "three", "0.5"))
    (field,) = edit.fields
    assert field.value is None and field.violation and field.violation.path == "Meter[1].count"


def test_a_line_that_differs_but_reads_the_same_is_unread(monkeypatch):
    edited = PLAN.text.replace(r"\hdPara{z}", r"\hdPara{z} % why")
    assert [(e.path, e.kind) for e in read(monkeypatch, edited, BASE)] == [("Para[2]", EditKind.UNREAD)]


def test_text_that_reads_as_the_same_value_is_unread(monkeypatch):
    edited = PLAN.text.replace("{0.5}", "{.5}")
    (edit,) = read(monkeypatch, edited, with_args(BASE, 5, "3cm", "3", ".5"))
    assert edit.kind is EditKind.UNREAD and edit.fields == ()


def test_a_removed_call_is_removed_once(monkeypatch):
    edited = PLAN.text.replace("\\hdPara{z}\n", "")
    assert [(e.path, e.kind) for e in read(monkeypatch, edited, without(BASE, 6))] == [("Para[2]", EditKind.REMOVED)]


def test_an_added_call_belongs_to_the_call_before_it(monkeypatch):
    extra = Call("hdPara", ("y",))
    edited = PLAN.text.replace("\\hdPara{z}\n", "\\hdPara{z}\n\\hdPara{y}\n")
    got = [*BASE, extra]
    assert [(e.path, e.kind) for e in read(monkeypatch, edited, got)] == [("Para[2]", EditKind.ADDED)]
    (first,) = read(monkeypatch, PLAN.text, [extra, *BASE])  # no line shows it: kept from the probe
    assert (first.path, first.kind, first.found) == ("document", EditKind.ADDED, "hdPara{y}")


def test_equal_calls_are_named_once_though_the_two_diffs_name_different_ones(monkeypatch):
    edited = PLAN.text.replace(
        "\\hdPara{a}\n", "", 1
    )  # the line diff names the first of the two equal lines or the second
    got = read(monkeypatch, edited, without(BASE, 2))
    assert [e.kind for e in got] == [EditKind.REMOVED]


def test_a_call_that_tex_does_not_run_is_removed_though_its_line_is_there(monkeypatch):
    edited = PLAN.text.replace("\\hdPara{z}\n", "\\iffalse\n\\hdPara{z}\n\\fi\n")
    got = list(read(monkeypatch, edited, without(BASE, 6)))
    assert [(e.path, e.kind) for e in got].count(("Para[2]", EditKind.REMOVED)) == 1
    assert [e.kind for e in got].count(EditKind.ADDED) == 2


def test_another_command_on_the_line_is_a_change_without_fields(monkeypatch):
    edited = PLAN.text.replace(r"\hdPara{z}", r"\hdNote{z}")
    (edit,) = read(monkeypatch, edited, [*BASE[:-1], Call("hdNote", ("", "z"))])
    assert (edit.kind, edit.fields, edit.found) == (EditKind.CHANGED, (), r"\hdNote{z}")


def test_an_environments_title_and_a_probe_only_change_are_read(monkeypatch):
    edited = PLAN.text.replace("{T}", "{TT}")
    (edit,) = read(monkeypatch, edited, with_args(BASE, 0, "TT"))
    assert (edit.path, [f.arg for f in edit.fields]) == ("Inner[0]", ["title"])
    kept = read(monkeypatch, PLAN.text, with_args(BASE, 3, "L", "m"))  # TeX read what the lines did not show
    assert [(e.path, e.kind, e.found) for e in kept] == [("Inner[0]/Note[2]", EditKind.CHANGED, "hdNote{L}{m}")]


def test_a_plan_whose_lines_and_calls_disagree_cannot_be_the_baseline(monkeypatch):
    monkeypatch.setattr(hand_edits, "_calls", lambda *_: BASE[:-1])
    with pytest.raises(TexmodelError) as raised:
        read_edits(NO_COMPILER, PLAN, PLAN.text, pkg)
    assert raised.value.code == "TM-X032"


def test_no_package_means_nothing_to_stub():
    with pytest.raises(TexmodelError) as raised:
        read_edits(NO_COMPILER, PLAN, PLAN.text)
    assert raised.value.code == "TM-X033"


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_tex_reads_a_hand_edited_document(compiler):  # noqa: F811
    edited = (
        PLAN.text.replace(r"\hdNote[L]{n}", r"\hdNote[L]{R\& D}")
        .replace(r"\hdPara{z}", r"\hdPara{z} % why")
        .replace(r"\hdMeter{3cm}{3}", r"\hdMeter{3cm}{three}")
    )
    edits = read_edits(compiler, PLAN, edited, pkg)
    got = {(e.path, e.kind): [(f.arg, f.value) for f in e.fields] for e in edits}
    assert got == {
        ("Inner[0]/Note[2]", EditKind.CHANGED): [("text", "R& D")],
        ("Para[2]", EditKind.UNREAD): [],
        ("Meter[1]", EditKind.CHANGED): [("count", None)],
    }
    assert [e.fields[0].violation.code for e in edits if e.path == "Meter[1]" and e.fields[0].violation] == ["TM-C021"]
    assert not re.search("Raw", repr(edits)) and RefKind.CALL
