"""Body pieces (M8): `TexRaw`, `Whitespace`, sequences and generators, and the package default."""

from texmodel.body import TemplateRef, TexRaw, Whitespace, join, pieces_of
from texmodel.components import Command, Environment
from texmodel.package import Package
from texmodel.types import Text

from .test_document import refused


def sty(body, **package) -> str:
    pkg = Package("body-demo", prefix="bd", **package)

    @pkg.command
    class Item(Command):
        """An item."""

        text: Text

        def body(self):  # noqa: ARG002
            return body

    return pkg.render()


def test_texraw_is_dedented_and_has_no_blank_edges():
    assert TexRaw("\n\n    a\n      b\n\n").body == "a\n  b"


def test_trim_adds_a_percent_to_each_line_except_where_it_is_not_wanted():
    piece = TexRaw(
        "\\par\\noindent   \n% a comment\n{\\bfseries #text}%\n\n100\\%",
        Whitespace.TRIM,
    )
    assert join([piece], Whitespace.KEEP, "x", str).splitlines() == [
        r"\par\noindent%",
        "% a comment",
        r"{\bfseries #text}%",
        "",
        r"100\%%",
    ]


def test_keep_writes_lines_as_given_and_is_the_default():
    text = "\\par\n  #text"
    assert join([TexRaw(text)], Whitespace.KEEP, "x", str) == text
    assert r"\newcommand{\bdItem}[1]{%" + "\n\\par\n  #1\n}" in sty(text)


def test_the_package_default_applies_to_pieces_that_name_none_and_a_piece_may_override_it():
    out = sty([TexRaw("\\a", Whitespace.KEEP), TexRaw("\\b"), "\\c #text"], whitespace=Whitespace.TRIM)
    assert out.endswith("\\a\n\\b%\n\\c #1%\n}\n")


def test_a_body_may_be_a_sequence_a_generator_or_an_iterator_of_pieces():
    def gen():
        yield "\\a"
        yield TexRaw("\\b #text", Whitespace.TRIM)

    assert sty(gen()).endswith("\\a\n\\b #1%\n}\n")
    assert sty(iter(["\\a #text", "\\b"])).endswith("\\a #1\n\\b\n}\n")
    assert sty(("\\a #text",)).endswith("\\a #1\n}\n")


def test_trim_refuses_verb():
    with refused("TM-M025"):
        sty(TexRaw("\\verb|x| #text", Whitespace.TRIM))


def test_a_template_ref_carries_a_policy_and_environments_take_pieces_too(tmp_path):
    (tmp_path / "a.tex").write_text("\\a #text\n")
    pkg = Package("body-demo", prefix="bd")

    @pkg.command
    class Item(Command):
        """An item."""

        text: Text
        body = TemplateRef(tmp_path / "a.tex", whitespace=Whitespace.TRIM)

    @pkg.environment
    class Box(Environment):
        """A box."""

        children = [Item.times.any()]
        begin = [TexRaw("\\begin{center}", Whitespace.TRIM)]
        end = "\\end{center}"

    out = pkg.render()
    assert "\\a #1%\n}" in out and "\\begin{center}%\n}{%\n\\end{center}\n}" in out


def test_what_is_not_a_body_is_refused():
    assert pieces_of(3) is None and pieces_of(["a", 3]) is None
    with refused("TM-M021"):
        sty(3)
