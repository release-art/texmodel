"""Specs (D2, S): a Doc from plain data and back, errors by path, and the JSON Schema."""

import json

import pytest

from texmodel.components import Command, Environment
from texmodel.package import Package
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import Raw, Text

pkg = Package("spec-demo", prefix="sd")


@pkg.command
class Fact(Command):
    """One fact."""

    body = "#text"
    text: Text


@pkg.command
class Icon(Command):
    """A picture by path."""

    body = "#path"
    path: Raw


@pkg.environment
class Face(Environment):
    """A face with a title and an optional note."""

    children = [Icon, Fact.times(3)]
    begin = r"\begin{center}#title #note"
    end = r"\end{center}"
    title: Text
    note: Raw | None = None


@pkg.environment
class Sheet(Environment):
    """Faces."""

    children = [Face.times.at_least_one()]
    begin = r"\begin{flushleft}"
    end = r"\end{flushleft}"


DATA = {
    "type": "Sheet",
    "content": [
        {
            "type": "Face",
            "title": "T",
            "note": "\\x",
            "content": [{"type": "Icon", "path": "a_b.jpg"}, {"type": "Fact", "text": "50%"}],
        },
        {"type": "Face", "title": "U", "content": [{"type": "Icon", "path": "c.jpg"}, {"type": "Fact", "text": "b"}]},
    ],
}


def test_a_document_loads_from_data_and_renders_like_the_same_tree_built_in_python():
    node = from_dict(Sheet, DATA)
    built = Sheet(
        Face(Icon(path=Raw("a_b.jpg")), Fact(text="50%"), title="T", note=Raw("\\x")),
        Face(Icon(path=Raw("c.jpg")), Fact(text="b"), title="U"),
    )
    assert node == built and node.render() == built.render() and node.violations() == []


def test_to_dict_round_trips_and_leaves_out_an_optional_none():
    node = from_dict(Sheet, DATA)
    assert to_dict(node) == DATA
    assert from_dict(Sheet, to_dict(node)) == node
    assert "note" not in to_dict(node)["content"][1]  # type: ignore[index]


def test_a_command_loads_on_its_own():
    assert from_dict(Fact, {"text": "x"}) == Fact(text="x")


def test_every_error_comes_at_once_with_the_path_validate_would_give():
    bad = {
        "content": [
            {"type": "Face", "title": 3, "content": [{"type": "Fact", "text": 4}, {"type": "Nope"}]},
            {"type": "Face", "content": []},
        ]
    }
    with pytest.raises(ExceptionGroup) as group:
        from_dict(Sheet, bad)
    found = sorted((e.path, e.code) for e in group.value.exceptions)  # pyright: ignore[reportAttributeAccessIssue]
    assert found == [
        ("Sheet/Face[0].title", "TM-C020"),
        ("Sheet/Face[0]/Fact[0].text", "TM-C020"),
        ("Sheet/Face[0]/content[1]", "TM-C020"),  # the unknown type
        ("Sheet/Face[1].title", "TM-C020"),
    ]


def test_unbalanced_raw_is_a_data_error_not_a_crash():
    with pytest.raises(ExceptionGroup) as group:
        from_dict(Icon, {"path": "{open"})
    (error,) = group.value.exceptions
    assert error.path == "Icon.path" and "unbalanced" in str(error)  # pyright: ignore[reportAttributeAccessIssue]


def test_raw_takes_a_string_or_a_raw_and_nothing_else():
    assert from_dict(Icon, {"path": Raw("a.jpg")}) == Icon(path=Raw("a.jpg"))
    with pytest.raises(ExceptionGroup) as group:
        from_dict(Icon, {"path": 3})
    assert "expected TeX as a string" in str(group.value.exceptions[0])


def test_a_missing_field_is_named():
    with pytest.raises(ExceptionGroup) as group:
        from_dict(Fact, {})
    assert [e.path for e in group.value.exceptions] == ["Fact.text"]  # pyright: ignore[reportAttributeAccessIssue]


def test_the_grammar_is_checked_by_validate_not_by_loading():
    node = from_dict(Sheet, {"content": []})
    assert [v.code for v in node.violations()] == ["TM-C002"]


def test_the_schema_has_docstrings_and_only_the_required_fields():
    face = json_schema(Face)
    assert face["properties"]["title"]["type"] == "string" and face["required"] == ["content", "title"]
    assert json_schema(Fact)["description"] == "One fact." and json_schema(Fact)["required"] == ["text"]
    json.dumps(json_schema(Sheet))  # serialisable, including the raw string type
