"""Components are frozen pydantic models (D1): positional construction, `fields_set`, what is refused."""

import pytest
from hypothesis import (
    given,
    strategies as st,
)

from texmodel.body import Comment
from texmodel.components import Command, Environment, Passthrough
from texmodel.errors import DeclarationError
from texmodel.interface import Star, arg
from texmodel.package import Package
from texmodel.spec import from_dict, to_dict
from texmodel.types import Length, Raw, Text

pkg = Package("models-demo", prefix="md")


@pkg.command
class Note(Command, unused=("starred",)):
    """A note."""

    body = "#text #label #gap"
    text: Text
    label: Text | None = arg(default=None, fill="")
    gap: Length = arg(default=Length("2mm"))
    starred: Star = arg(default=False)


@pkg.environment
class Box(Environment):
    """A box."""

    children = [Note.times.any(), Passthrough.times.any()]
    begin = r"\begin{center}#title"
    end = r"\end{center}"
    title: Text | None = None


def test_fields_set_is_what_the_caller_passed_positionally_or_by_keyword():
    assert Note(text="x").fields_set == {"text"}
    assert Note(text="x", label=None).fields_set == {"text", "label"}  # a default given is the caller's
    assert Note(text="x", gap=Length("2mm")).fields_set == {"text", "gap"}
    assert Box(Note(text="x")).fields_set == {"content"} and Box(title="T").fields_set == {
        "content",
        "title",
    }
    assert Passthrough(Raw(r"\par")).fields_set == {"tex"}


def test_fields_set_from_data_is_the_keys_the_data_gave_and_to_dict_writes_them():
    node = from_dict(Box, {"title": "T", "content": [{"type": "Note", "text": "x", "label": None}]})
    assert isinstance(node, Box) and node.fields_set == {"content", "title"}
    assert isinstance(note := node.content[0], Note) and note.fields_set == {"text", "label"}
    assert to_dict(node) == {
        "type": "Box",
        "title": "T",
        "content": [{"type": "Note", "text": "x", "label": None}],
    }


@given(
    label=st.none() | st.text(max_size=3) | st.just(...),
    starred=st.booleans() | st.just(...),
    gap=st.sampled_from([Length("2mm"), Length("1pt")]) | st.just(...),
)
def test_a_round_trip_through_data_keeps_the_tree_and_its_fields_set(label: object, starred: object, gap: object):
    given_fields = {k: v for k, v in {"label": label, "starred": starred, "gap": gap}.items() if v is not ...}
    node = Box(Note(text="x", **given_fields), Passthrough(Raw(r"\par")))  # pyright: ignore[reportArgumentType]
    back = from_dict(Box, to_dict(node))
    assert isinstance(back, Box) and back == node
    assert [c.fields_set for c in back.content] == [c.fields_set for c in node.content]  # pyright: ignore[reportAttributeAccessIssue]


def test_a_comment_child_dumps_its_fields():
    assert to_dict(Box(Note(text="x"), Comment("c")))["content"] == [
        {"type": "Note", "text": "x"},
        {"type": "Comment", "text": "c"},
    ]


def test_construction_does_not_validate_data_does():
    assert [v.code for v in Note(text=3).violations()] == ["TM-C003"]  # pyright: ignore[reportArgumentType]
    with pytest.raises(ExceptionGroup) as info:
        from_dict(Note, {"text": 3})
    assert [e.code for e in info.value.exceptions] == ["TM-C020"]  # pyright: ignore[reportAttributeAccessIssue]


def test_construction_refuses_what_a_signature_would():
    # pyright flags the first three (the ignores); an environment's keywords it cannot check (known limitations)
    for build, message in (
        (lambda: Note("x"), "takes 0 positional argument"),  # pyright: ignore[reportCallIssue]
        (lambda: Note(text="x", txt="y"), "unexpected keyword arguments ['txt']"),  # pyright: ignore[reportCallIssue]
        (lambda: Note(), "missing arguments ['text']"),  # pyright: ignore[reportCallIssue]
        (lambda: Box(content=()), "unexpected keyword arguments ['content']"),  # children are positional
        (lambda: Box(titel="T"), "unexpected keyword arguments ['titel']"),
    ):
        with pytest.raises(TypeError, match=message.replace("[", r"\[").replace("]", r"\]")):
            build()


def test_equality_and_hash_are_structural_and_ignore_fields_set():
    assert Note(text="x") == Note(text="x", label=None) and hash(Note(text="x")) == hash(Note(text="x", label=None))
    assert Note(text="x") != Note(text="y") and Box(Note(text="x")) != Box(Note(text="y"))
    shown = repr(Box(Passthrough(Raw(r"\par")), title="T"))
    assert str(Box(Passthrough(Raw(r"\par")), title="T")) == shown == r"Box(Passthrough(Raw(tex='\\par')), title='T')"


@pytest.mark.parametrize("name", ["copy", "render", "violations", "fields_set", "meta", "json", "model_fields"])
def test_a_field_named_like_an_attribute_of_every_component_is_refused(name: str):
    with pytest.raises(DeclarationError) as info:
        type(f"Bad{name.title()}", (Command,), {"__doc__": "Bad.", "__annotations__": {name: Text}})
    assert info.value.code == "TM-M045" and f".{name}" in str(info.value)


def test_a_field_may_start_with_model():
    class Modelled(Command):
        """A name pydantic would warn about in a model of its own."""

        model_kind: Text

    assert Modelled(model_kind="a").fields_set == {"model_kind"}
    assert from_dict(Modelled, {"model_kind": "a"}) == Modelled(model_kind="a")
