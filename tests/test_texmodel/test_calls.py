"""The calls a document writes, read from its tokens (`_internal.calls`), and the edits read from them without TeX."""

import typing

from texmodel._internal.calls import ParsedCall, Unreadable, parse_calls
from texmodel.body import RefKind
from texmodel.components import Command, Environment, Passthrough, control_name
from texmodel.interface import ANGLE, PAREN, Star, arg
from texmodel.package import Package
from texmodel.plan import EditKind
from texmodel.run.hand_edits import read_written_edits
from texmodel.testing import Call, expand
from texmodel.types import Length, Text

pkg = Package("wr", prefix="wr")


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
class Angle(Command):
    """An optional argument in angle brackets."""

    text: Text
    mark: Text | None = arg(ANGLE, default=None)
    body = r"\par #mark #text\par"


@pkg.command
class Stars(Command):
    """A starred command with a delimited required argument."""

    starred: Star = False
    at: Text = arg(PAREN)
    size: Length | None = None
    body = r"\par #starred #at #size\par"


@pkg.environment
class Box(Environment):
    """A box."""

    title: Text
    children = [Para.times.any()]
    begin = r"\begin{center}#title"
    end = r"\end{center}"


CLASSES = {control_name(c): c for c in (Para, Note, Angle, Stars, Box)}


def read(text: str) -> list[ParsedCall | Unreadable]:
    return list(parse_calls(text, CLASSES))


def calls(text: str) -> list[Call]:
    return [p.call for p in read(text) if isinstance(p, ParsedCall)]


def test_required_arguments_are_a_group_or_one_token_and_shown_as_detokenize_shows_them():
    got = calls("\\wrPara{ a  b }\\wrPara x\n\\wrPara\n  {R\\& D}\\wrPara\\relax\\wrPara{{x}}\\wrPara{a%c\n b}")
    assert [c.args for c in got] == [(" a b ",), ("x",), ("R\\& D",), ("\\relax ",), ("{x}",), ("ab",)]


def test_a_blank_line_is_a_paragraph_and_a_comment_a_line_end_that_is_one_too():
    assert calls("\\wrPara{a\n\nb}\\wrPara{a%\n\nb}\\wrPara{a\n\n\nb}")[0].args == ("a \\par b",)
    assert [c.args[0] for c in calls("\\wrPara{a\n\nb}\\wrPara{a%\n\nb}\\wrPara{a\n\n\nb}")] == [
        "a \\par b",
        "a\\par b",
        "a \\par \\par b",
    ]


def test_an_optional_argument_is_read_when_its_delimiter_comes_next_and_has_its_default_otherwise():
    got = calls("\\wrNote{n}\\wrNote [L] {n}\\wrNote[{a]b}]{n}\\wrNote[]{n}\\wrAngle{n} <m>\\wrAngle{n}")
    # `arg()` keeps a slot where it is declared; an unplaced optional field is TeX's first argument
    assert [c.args for c in got] == [("", "n"), ("L", "n"), ("a]b", "n"), ("", "n"), ("n", "m"), ("n", "")]


def test_a_token_slot_is_true_when_written_and_a_delimited_argument_needs_its_delimiter():
    got = calls("\\wrStars[3cm]*(x)\\wrStars (y)\\wrStars{z}")  # the unplaced optional `size` comes first
    assert [c.args for c in got] == [("3cm", "\\BooleanTrue ", "x"), ("", "\\BooleanFalse ", "y")]
    (bad,) = (p for p in read("\\wrStars{z}") if isinstance(p, Unreadable))
    assert bad.name == "wrStars" and "needs its (" in bad.why


def test_an_environment_is_its_begin_with_arguments_and_its_end_without():
    got = calls("\\begin {wrBox} {T}\\wrPara{a}\\end {wrBox}\\begin{center}\\end{center}\\begin{wrBox")
    assert calls("\\begin x\\end") == []
    assert [(c.kind, c.name, c.args) for c in got] == [
        (RefKind.OPEN, "wrBox", ("T",)),
        (RefKind.CALL, "wrPara", ("a",)),
        (RefKind.CLOSE, "wrBox", ()),
    ]


def test_what_does_not_run_is_not_a_call():
    text = (
        "% \\wrPara{c}\n\\wrPara{a}% \\wrPara{t}\n\\verb|\\wrPara{v}|\n\\newif\\ifx\n"
        "\\iffalse \\wrPara{d1} \\fi\n\\iffalse \\wrPara{d2} \\else \\wrPara{live} \\fi"
    )
    assert [c.args[0] for c in calls(text)] == ["a", "live"]


def test_spans_say_where_each_written_argument_is():
    text = "x \\wrNote[L]{n} y"
    (one,) = (p for p in read(text) if isinstance(p, ParsedCall))
    assert text[one.start : one.end] == "\\wrNote[L]{n}"
    assert [text[s[0] : s[1]] for s in one.spans if s] == ["L", "n"]
    (bare,) = (p for p in read("\\wrNote{n}") if isinstance(p, ParsedCall))
    assert bare.spans[0] is None and bare.call.args == ("", "n")


def test_what_cannot_be_read_is_reported_with_where():
    why = [read(t)[0] for t in ("\\wrNote[L{n}", "\\wrPara{open", "\\wrPara}", "\\wrPara")]
    assert [p.why for p in why if isinstance(p, Unreadable)] == [
        "no ] closes the [ of label",
        "the { of text never closes",
        "text is missing",
        "text is missing",
    ]
    assert calls("\\wrPara\\wrNote{n}")[0].args == ("\\wrNote ",)  # TeX takes the next token as the argument


NODES = (Box(Para(text="a"), title="T"), Note(text="n", label="L"), Para(text="z"))
PLAN = pkg.plan(*NODES)
BASE = [c for n in NODES for c in expand(n, [Para, Note, Angle, Stars, Box]) if isinstance(c, Call)]


def edits(text: str) -> list[tuple[str, EditKind]]:
    return [(e.path, e.kind) for e in read_written_edits(PLAN, text, pkg)]


def test_the_plan_reads_as_the_calls_the_stub_tier_expects_of_it():
    assert [p.call for p in read(PLAN.text) if isinstance(p, ParsedCall)] == BASE


def test_written_edits_name_the_field_and_the_typed_value_without_a_compile():
    (edit,) = read_written_edits(PLAN, PLAN.text.replace(r"\wrNote[L]{n}", r"\wrNote[LL]{n}"), pkg)
    assert (edit.path, edit.kind) == ("Note[1]", EditKind.CHANGED)
    assert [(f.arg, f.found, f.value) for f in edit.fields] == [("label", "LL", "LL")]


def test_written_edits_see_comments_removals_and_calls_tex_will_not_run():
    z = r"\wrPara{z}"
    assert edits(PLAN.text.replace(z, z + " % why")) == [("Para[2]", EditKind.UNREAD)]
    assert edits(PLAN.text.replace(z + "\n", "")) == [("Para[2]", EditKind.REMOVED)]
    assert edits(PLAN.text.replace(z + "\n", "% " + z + "\n")) == [("Para[2]", EditKind.REMOVED)]
    assert edits(PLAN.text.replace(z + "\n", z + "\n" + z + "\n")) == [("Para[2]", EditKind.ADDED)]
    assert edits(PLAN.text.replace(z + "\n", "\\iffalse\n" + z + "\n\\fi\n")).count(("Para[2]", EditKind.REMOVED)) == 1


def test_a_package_of_no_components_has_nothing_to_read():
    import pytest

    from texmodel.errors import TexmodelError

    with pytest.raises(TexmodelError) as raised:
        read_written_edits(PLAN, PLAN.text)
    assert raised.value.code == "TM-X033"
    assert typing.cast("object", Passthrough)  # the grammar of Box allows only Para
