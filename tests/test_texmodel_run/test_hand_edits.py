"""Hand edits read by TeX: the merge of calls and lines without TeX, and one compile."""

import re
import typing

import pytest

from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401
from texmodel.body import RefKind
from texmodel.components import Command, Environment, Passthrough
from texmodel.errors import TexmodelError
from texmodel.package import Package
from texmodel.plan import EditKind
from texmodel.run import hand_edits
from texmodel.run.compiler import Compiler
from texmodel.run.diagnostics import Measurement
from texmodel.run.hand_edits import read_edits
from texmodel.testing import Call, expand
from texmodel.types import Length, Text

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
NODES = (
    Inner(Para(text="a"), Para(text="a"), Note(text="n", label="L"), title="T"),
    Meter(width=Length("3cm"), count=3, ratio=0.5),
    Para(text="z"),
)
PLAN = pkg.plan(*NODES)
BASE = [c for n in NODES for c in expand(n, STUBS) if isinstance(c, Call)]
NO_COMPILER = typing.cast("Compiler", None)


async def read(monkeypatch: pytest.MonkeyPatch, edited: str, calls: list[Call]):
    answers = iter([BASE, calls])  # the plan's own text first, then the edited one

    async def calls_of(*_: object) -> list[Call]:
        return next(answers)

    monkeypatch.setattr(hand_edits, "_calls", calls_of)
    return await read_edits(NO_COMPILER, PLAN, edited, pkg)


def without(calls: list[Call], *indexes: int) -> list[Call]:
    return [c for i, c in enumerate(calls) if i not in indexes]


def with_args(calls: list[Call], index: int, *args: str) -> list[Call]:
    return [Call(c.name, args, c.kind) if i == index else c for i, c in enumerate(calls)]


async def test_the_probe_names_the_argument_with_its_typed_value(monkeypatch):
    edited = PLAN.text.replace(r"\hdNote[L]{n}", r"\hdNote[LL]{n}")
    (edit,) = await read(monkeypatch, edited, with_args(BASE, 3, "LL", "n"))
    assert (edit.path, edit.kind) == ("Inner[0]/Note[2]", EditKind.CHANGED)
    assert [(f.arg, f.found, f.value) for f in edit.fields] == [("label", "LL", "LL")]
    assert edit.expected == r"  \hdNote[L]{n}" and edit.found == r"  \hdNote[LL]{n}"


async def test_a_value_that_is_not_of_the_type_carries_a_violation_at_the_field(monkeypatch):
    edited = PLAN.text.replace("{3}", "{three}")
    (edit,) = await read(monkeypatch, edited, with_args(BASE, 5, "3cm", "three", "0.5"))
    (field,) = edit.fields
    assert field.value is None and field.violation and field.violation.path == "Meter[1].count"


async def test_a_line_that_differs_but_reads_the_same_is_unread(monkeypatch):
    edited = PLAN.text.replace(r"\hdPara{z}", r"\hdPara{z} % why")
    assert [(e.path, e.kind) for e in await read(monkeypatch, edited, BASE)] == [("Para[2]", EditKind.UNREAD)]


async def test_text_that_reads_as_the_same_value_is_unread(monkeypatch):
    edited = PLAN.text.replace("{0.5}", "{.5}")
    (edit,) = await read(monkeypatch, edited, with_args(BASE, 5, "3cm", "3", ".5"))
    assert edit.kind is EditKind.UNREAD and edit.fields == ()


async def test_a_removed_call_is_removed_once(monkeypatch):
    edited = PLAN.text.replace("\\hdPara{z}\n", "")
    assert [(e.path, e.kind) for e in await read(monkeypatch, edited, without(BASE, 6))] == [
        ("Para[2]", EditKind.REMOVED)
    ]


async def test_an_added_call_belongs_to_the_call_before_it(monkeypatch):
    extra = Call("hdPara", ("y",))
    edited = PLAN.text.replace("\\hdPara{z}\n", "\\hdPara{z}\n\\hdPara{y}\n")
    got = [*BASE, extra]
    assert [(e.path, e.kind) for e in await read(monkeypatch, edited, got)] == [("Para[2]", EditKind.ADDED)]
    (first,) = await read(monkeypatch, PLAN.text, [extra, *BASE])  # no line shows it: kept from the probe
    assert (first.path, first.kind, first.found) == ("document", EditKind.ADDED, "hdPara{y}")


async def test_equal_calls_are_named_once_though_the_two_diffs_name_different_ones(monkeypatch):
    edited = PLAN.text.replace(
        "  \\hdPara{a}\n", "", 1
    )  # the line diff names the first of the two equal lines or the second
    got = await read(monkeypatch, edited, without(BASE, 2))
    assert [e.kind for e in got] == [EditKind.REMOVED]


async def test_a_call_that_tex_does_not_run_is_removed_though_its_line_is_there(monkeypatch):
    edited = PLAN.text.replace("\\hdPara{z}\n", "\\iffalse\n\\hdPara{z}\n\\fi\n")
    got = list(await read(monkeypatch, edited, without(BASE, 6)))
    assert [(e.path, e.kind) for e in got].count(("Para[2]", EditKind.REMOVED)) == 1
    assert [e.kind for e in got].count(EditKind.ADDED) == 2


async def test_a_call_commented_out_is_one_removal_of_its_line(monkeypatch):
    edited = PLAN.text.replace("\\hdPara{z}\n", "% \\hdPara{z}\n")
    (edit,) = await read(monkeypatch, edited, without(BASE, 6))
    assert (edit.path, edit.kind, edit.found) == ("Para[2]", EditKind.REMOVED, "% \\hdPara{z}")


async def test_another_command_on_the_line_is_a_change_without_fields(monkeypatch):
    edited = PLAN.text.replace(r"\hdPara{z}", r"\hdNote{z}")
    (edit,) = await read(monkeypatch, edited, [*BASE[:-1], Call("hdNote", ("", "z"))])
    assert (edit.kind, edit.fields, edit.found) == (EditKind.CHANGED, (), r"\hdNote{z}")


async def test_an_environments_title_and_a_probe_only_change_are_read(monkeypatch):
    edited = PLAN.text.replace("{T}", "{TT}")
    (edit,) = await read(monkeypatch, edited, with_args(BASE, 0, "TT"))
    assert (edit.path, [f.arg for f in edit.fields]) == ("Inner[0]", ["title"])
    kept = await read(monkeypatch, PLAN.text, with_args(BASE, 3, "L", "m"))  # TeX read what the lines did not show
    assert [(e.path, e.kind, e.found) for e in kept] == [("Inner[0]/Note[2]", EditKind.CHANGED, "hdNote{L}{m}")]


async def test_a_plan_whose_lines_and_calls_disagree_cannot_be_the_baseline(monkeypatch):
    async def one_short(*_: object) -> list[Call]:
        return BASE[:-1]

    monkeypatch.setattr(hand_edits, "_calls", one_short)
    with pytest.raises(TexmodelError) as raised:
        await read_edits(NO_COMPILER, PLAN, PLAN.text, pkg)
    assert raised.value.code == "TM-X032"


async def test_calls_are_the_numbered_probes_in_order_with_the_stubs_before_the_document(monkeypatch):
    seen: list[str] = []

    async def fake_probes(_unused, tex, files):
        seen.append(tex)
        probes = [("call10", "hdPara{b}"), ("other", "x"), ("call2", "begin:hdInner{T}"), ("call1", "hdPara{a}")]
        return [Measurement(message="", name=n, value=v) for n, v in probes]

    monkeypatch.setattr(hand_edits, "run_probes", fake_probes)
    calls = await hand_edits._calls(NO_COMPILER, "\\begin{document}\nx", [Para, Inner], {})
    assert [c.name for c in calls] == ["hdPara", "hdInner", "hdPara"]
    assert calls[1].kind is RefKind.OPEN
    assert seen[0].index("hdPara") < seen[0].index("\\begin{document}")


async def test_no_package_means_nothing_to_stub():
    with pytest.raises(TexmodelError) as raised:
        await read_edits(NO_COMPILER, PLAN, PLAN.text)
    assert raised.value.code == "TM-X033"


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_tex_reads_a_hand_edited_document(compiler):  # noqa: F811
    edited = (
        PLAN.text.replace(r"\hdNote[L]{n}", r"\hdNote[L]{R\& D}")
        .replace(r"\hdPara{z}", r"\hdPara{z} % why")
        .replace(r"\hdMeter{3cm}{3}", r"\hdMeter{3cm}{three}")
    )
    edits = await read_edits(compiler, PLAN, edited, pkg)
    got = {(e.path, e.kind): [(f.arg, f.value) for f in e.fields] for e in edits}
    assert got == {
        ("Inner[0]/Note[2]", EditKind.CHANGED): [("text", "R& D")],
        ("Para[2]", EditKind.UNREAD): [],
        ("Meter[1]", EditKind.CHANGED): [("count", None)],
    }
    assert [e.fields[0].violation.code for e in edits if e.path == "Meter[1]" and e.fields[0].violation] == ["TM-C021"]
    assert not re.search("Raw", repr(edits)) and RefKind.CALL
