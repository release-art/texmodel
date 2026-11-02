"""The calls a document writes, read from its tokens (`_internal.calls`), and the edits read from them without TeX."""

from texmodel._internal.calls import MADE_BY_MACRO, ParsedCall, Unreadable, parse_calls
from texmodel.body import RefKind
from texmodel.components import Command, Environment, control_name
from texmodel.interface import ANGLE, PAREN, Star, arg
from texmodel.package import Package
from texmodel.testing import Call
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


def test_a_parameter_character_is_shown_doubled_and_a_no_break_space_is_kept():
    assert [c.args[0] for c in calls("\\wrPara{#1 ##2}\\wrPara{a\u00a0 b}")] == ["##1 ####2", "a\u00a0 b"]


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


def test_a_call_inside_a_definition_is_made_by_a_macro_and_is_not_read():
    text = (
        r"\newcommand*{\x}[2][d]{\wrPara{#1}}\def\y#1.#2{\wrNote{#1}{#2}}\wrPara{live}"
        r"\newenvironment{e}[1]{\begin{wrBox}{T}}{\end{wrBox}}"
        r"\NewDocumentCommand\z{m}{\wrPara{#1}}\NewDocumentEnvironment{f}{}{\wrPara{x}}{\wrPara{y}}\wrPara{after}"
    )
    got = [(type(p).__name__, p.name if isinstance(p, Unreadable) else p.call.args[0]) for p in read(text)]
    assert got == [
        ("Unreadable", "wrPara"),
        ("Unreadable", "wrNote"),
        ("ParsedCall", "live"),
        ("Unreadable", "wrBox"),
        ("Unreadable", "wrBox"),
        ("Unreadable", "wrPara"),
        ("Unreadable", "wrPara"),
        ("Unreadable", "wrPara"),
        ("ParsedCall", "after"),
    ]
    assert {p.why for p in read(text) if isinstance(p, Unreadable)} == {MADE_BY_MACRO}


def test_a_definition_that_never_closes_holds_the_rest_of_the_text():
    for text in (
        r"\newcommand{\x}{\wrPara{a}",
        r"\def\x#1",
        r"\newcommand{\x}[1",
        r"\newcommand",
        r"\newenvironment{e}{}",
    ):
        assert not calls(text + r"\wrPara{b}")


def test_a_component_copied_by_let_is_no_call():
    assert [c.args[0] for c in calls(r"\let\p\wrPara \let\q=\wrPara \let\wrPara\relax \wrPara{b}\let")] == ["b"]
