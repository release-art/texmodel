"""`Comment` (§21a 21): prefixed lines, templates, a body piece, a transparent document node, and data."""

import dataclasses

import pytest
from hypothesis import (
    given,
    strategies as st,
)

from texmodel.body import Comment, Whitespace
from texmodel.components import Command, Environment
from texmodel.package import Package
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import Text

from .test_document import refused


class Header(Comment):
    """The audit block above a card."""

    template = """
        Card: #name
          id: ## #id
    """
    name: str
    id: str


def small():
    pkg = Package("com", prefix="cm")

    @pkg.command
    class Item(Command):
        """An item."""

        body = "#text"
        text: Text

    @pkg.environment
    class Box(Environment):
        """A box."""

        children = [Item, Item.times(2)]
        begin = r"\begin{center}"
        end = r"\end{center}"

    return pkg, Item, Box


# --- prefixing -----------------------------------------------------------------------------------------------


def test_a_comment_prefixes_every_line_dedents_and_drops_blank_edges():
    assert Comment("\n\n    one\n\n      two\n\n").lines() == ("% one", "%", "%   two")
    assert Comment("x").render() == "% x"
    assert Comment("").render() == ""


@given(st.text())
def test_a_value_cannot_leave_the_comment(value):
    lines = Comment(value).lines()
    assert all(line.startswith("%") for line in lines)
    assert len("\n".join(lines).splitlines()) == len(lines)


def test_a_comment_is_a_frozen_value():
    c = Comment("a")
    assert (c, hash(c), repr(c)) == (Comment("a"), hash(Comment("a")), "Comment('a')")
    assert c != Comment("b") and c != Header("a", "b")
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.text = "b"  # type: ignore[misc]
    assert c.validate() == []


# --- templates -----------------------------------------------------------------------------------------------


def test_a_template_fills_its_holes_and_keeps_a_double_hash_as_one():
    assert Header("Fox", "7").lines() == ("% Card: Fox", "%   id: # 7")
    assert Header("a\nb", "7").lines()[:2] == ("% Card: a", "% b")
    assert repr(Header("Fox", "7")) == "Header(name='Fox', id='7')"


def test_a_hole_that_is_not_a_field_and_an_unused_field_are_refused():
    with refused("TM-M028"):

        class Unknown(Comment):
            """x"""

            template = "#nope"
            a: str

    with refused("TM-M028"):

        class Unused(Comment):
            """x"""

            template = "text"
            a: str

    with refused("TM-M028"):

        class NoTemplate(Comment):
            """x"""

            a: str


def test_a_field_missing_from_the_call_is_the_dataclass_error():
    with pytest.raises(TypeError):
        Header("Fox")  # type: ignore[call-arg]


# --- body piece ----------------------------------------------------------------------------------------------


def test_a_comment_in_a_body_is_written_at_its_position():
    pkg = Package("note", prefix="nt", whitespace=Whitespace.TRIM)

    @pkg.command
    class Item(Command):
        """An item."""

        text: Text

        def body(self):  # noqa: ARG002
            yield "\\par"
            yield Comment("see issue #12\nand #1 more")
            yield "#text"

    sty = pkg.render()
    assert "{%\n\\par%\n% see issue #12\n% and #1 more\n#1%\n}" in sty


# --- document node -------------------------------------------------------------------------------------------


def test_a_comment_child_is_not_counted_and_does_not_break_the_order():
    pkg, item, box = small()
    plain = box(item("a"), item("b"))
    for node in (
        box(Comment("first"), item("a"), Comment("mid"), item("b"), Comment("last")),
        box(Header("x", "1"), item("a"), item("b")),
    ):
        assert node.validate() == []
        assert [ln for ln in node.render().splitlines() if not ln.startswith("%")] == plain.render().splitlines()
    assert box(Comment("c")).validate()[0].code == "TM-C002"  # still one required Item
    (bad,) = box(item("a"), Comment("c"), item("b"), item("c"), item("d")).validate()
    assert bad.path == "Box/Item[4]"  # the real position, comments counted in the index


def test_a_comment_has_a_plan_path_on_each_of_its_lines():
    pkg, item, box = small()
    plan = pkg.plan(Header("x", "1"), box(item("a"), Comment("p\nq"), item("b")))
    paths = [(x.path, x.tex) for x in plan.lines if x.tex.startswith("%") and not x.tex.startswith("% com")]
    assert paths == [
        ("Header[0]", "% Card: x"),
        ("Header[0]", "%   id: # 1"),
        ("Box[1]/Comment[1]", "% p"),
        ("Box[1]/Comment[1]", "% q"),
    ]


def test_the_interface_check_does_not_see_comments():
    pkg, _, _ = small()
    assert pkg.check_interface(pkg.render()) == []


# --- edits ---------------------------------------------------------------------------------------------------


def test_edits_can_ignore_comment_lines():
    pkg, item, box = small()
    plan = pkg.plan(Header("x", "1"), box(item("a"), item("b")))
    assert plan.edits(plan.text) == []
    changed = plan.text.replace("Card: x", "Card: someone else")
    assert [e.path for e in plan.edits(changed)] == ["Header[0]"]
    assert plan.edits(changed, ignore_comments=True) == []
    as_text = plan.text.replace("% Card: x", "Card: x")
    (edit,) = plan.edits(as_text, ignore_comments=True)
    assert (edit.path, edit.expected, edit.found) == ("Header[0]", "% Card: x", "Card: x")


# --- data ----------------------------------------------------------------------------------------------------


def test_a_comment_child_round_trips_through_data_and_the_schema():
    _, item, box = small()
    node = box(Header("x", "1"), item("a"), Comment("note"), item("b"))
    data = to_dict(node)
    assert data["content"][0] == {"type": "Header", "name": "x", "id": "1"}  # type: ignore[index]
    assert from_dict(box, data, comments=[Header]) == node
    defs = json_schema(box, comments=[Header])["$defs"]
    assert set(defs) >= {"Header", "Comment"} and defs["Header"]["required"] == ["name", "id"]
    assert [c for c in from_dict(box, data, comments=[Header]).content if isinstance(c, Comment)] == [  # type: ignore[union-attr]
        Header("x", "1"),
        Comment("note"),
    ]


def test_a_comment_type_nobody_listed_is_reported_by_path():
    _, item, box = small()
    data = {"content": [{"type": "Header", "name": "x", "id": "1"}, to_dict(item("a")), to_dict(item("b"))]}
    with pytest.raises(ExceptionGroup):
        from_dict(box, data)
