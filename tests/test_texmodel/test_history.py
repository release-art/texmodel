"""`texmodel.history` (§13 X5, X11): what stops stored data from being a valid tree, and what changed between two
schemas of one model. texpkg runs migrations over these."""

import copy
import enum

import pytest

from texmodel.components import Command, Environment, field
from texmodel.history import (
    Change,
    Level,
    Problem,
    pointer,
    problems,
    schema_at,
    schema_changes,
    unplaced,
    violation_pointer,
    worst,
)
from texmodel.package import Package
from texmodel.spec import json_schema, to_dict
from texmodel.types import Choice, Raw, Text

pkg = Package("acme-history", prefix="ah")


@enum.unique
class Accent(Choice):
    """A fact's accent colour."""

    SLATE = Raw("slate")
    MOSS = Raw("moss")


@pkg.command
class Name(Command):
    """A card's name."""

    text: Text
    body = "#text"


@pkg.command
class Fact(Command):
    """A fact."""

    text: Text
    accent: Accent = Accent.SLATE
    body = "#text #accent"


@pkg.environment
class Card(Environment):
    """A card."""

    children = [Name, Fact.times(1, 2)]
    begin = "x"
    end = "y"


@pkg.environment
class Deck(Environment):
    """A deck."""

    children = [Card.times.any()]
    begin = "x"
    end = "y"


SCHEMA = json_schema(Deck)
DATA = to_dict(Deck(Card(Name(text="Owl"), Fact(text="Hoots."))))


def stored() -> dict[str, object]:
    return copy.deepcopy(DATA)


def test_valid_data_has_no_problems():
    assert problems(Deck, DATA, SCHEMA) == [] and unplaced(DATA, SCHEMA) == []


def test_a_value_the_model_refuses_is_a_problem_with_its_constraint():
    data = stored()
    data["content"][0]["content"][1]["accent"] = "PINK"  # pyright: ignore[reportIndexIssue]
    (found,) = problems(Deck, data, SCHEMA)
    assert (found.path, found.value) == ("/content/0/content/1/accent", "PINK")
    assert found.schema["enum"] == ["SLATE", "MOSS"] and "SLATE" in found.reason


def test_a_grammar_violation_is_a_problem_at_its_node():
    data = stored()
    data["content"][0]["content"] = data["content"][0]["content"][:1]  # pyright: ignore[reportIndexIssue]
    assert problems(Deck, data, SCHEMA) == [Problem("/content/0", "Card: expected 1-2 Fact, found 0")]


def test_a_stored_field_the_model_no_longer_has_is_reported_not_dropped():
    data = stored()
    data["content"][0]["content"][1]["note"] = "keep this sentence"  # pyright: ignore[reportIndexIssue]
    data["$defaults"] = {}  # texpkg's record of the values at their default, not a field
    (found,) = unplaced(data, SCHEMA)
    assert (found.path, found.value) == ("/content/0/content/1/note", "keep this sentence")
    assert "has to place it or remove it on purpose" in found.reason
    assert problems(Deck, data, SCHEMA) == []  # validation would drop it without a word


def test_a_node_of_an_unknown_class_is_left_to_the_validation():
    assert unplaced({"type": "Gone", "extra": 1}, SCHEMA) == []


def test_locations_become_data_paths():
    assert pointer(("content", 1, "Card", "content", 0, "Title", "text")) == "/content/1/content/0/text"
    assert pointer(("content",)) == "/content" and pointer(()) == ""
    assert violation_pointer("Deck") == "" and violation_pointer("Deck/Card[1]/Fact[0]") == "/content/1/content/0"


def test_the_schema_of_a_field_is_found_or_empty():
    schema = {"$defs": {"Fact": {"properties": {"accent": {"enum": ["a"]}}}}, "properties": {"content": {}}}
    assert schema_at(schema, ("content", 1, "Fact", "accent")) == {"enum": ["a"]}
    assert schema_at(schema, ("content", 1, "Nothing", "accent")) == {}
    assert schema_at(schema, ("content",)) == {} and schema_at(schema, ()) == {}


FIELD = {"type": "string", "title": "Text"}


def fact(**properties: object) -> dict[str, object]:
    return {"title": "Fact", "type": "object", "properties": properties, "required": ["text"], "$defs": {}}


@pytest.mark.parametrize(
    ("old", "new", "level", "words"),
    [
        (fact(text=FIELD), fact(text=FIELD), Level.NONE, ""),
        (fact(text=FIELD), fact(text=FIELD, note={"type": "string"}), Level.COMPATIBLE, "added"),
        (fact(text=FIELD, note={}), fact(text=FIELD), Level.BREAKING, "removed"),
        (fact(text=FIELD), fact(text={"type": "integer", "title": "Text"}), Level.BREAKING, "type changed"),
        (fact(text={**FIELD, "maxLength": 100}), fact(text={**FIELD, "maxLength": 70}), Level.BREAKING, "maxLength"),
        (fact(text={**FIELD, "maxLength": 70}), fact(text={**FIELD, "maxLength": 100}), Level.COMPATIBLE, "maxLength"),
        (fact(text={**FIELD, "minLength": 1}), fact(text={**FIELD, "minLength": 3}), Level.BREAKING, "minLength"),
        (fact(text={**FIELD, "maxItems": 3}), fact(text={**FIELD, "maxItems": 2}), Level.BREAKING, "maxItems"),
        (fact(text={**FIELD, "enum": ["a", "b"]}), fact(text={**FIELD, "enum": ["a"]}), Level.BREAKING, "no longer"),
        (fact(text={**FIELD, "enum": ["a"]}), fact(text={**FIELD, "enum": ["a", "b"]}), Level.COMPATIBLE, "added"),
        (fact(text={**FIELD, "default": "a"}), fact(text={**FIELD, "default": "b"}), Level.REVISION, "default"),
        (fact(text=FIELD), fact(text={**FIELD, "description": "the name"}), Level.REVISION, "description"),
        (
            fact(text=FIELD, note={}),
            {**fact(text=FIELD, note={}), "required": ["text", "note"]},
            Level.BREAKING,
            "required",
        ),
        (fact(text=FIELD), {**fact(text=FIELD, note={}), "required": ["text", "note"]}, Level.BREAKING, "required"),
        (fact(text=FIELD, old={}), fact(text=FIELD, new={"x-renamed-from": "old"}), Level.COMPATIBLE, "renamed"),
        (
            fact(text=FIELD, box={"properties": {"a": {}, "b": {}}}),
            fact(text=FIELD, box={"properties": {"a": {}, "c": {}}}),
            Level.BREAKING,
            "removed",
        ),
    ],
)
def test_a_schema_change_is_classified_as_avro_does(old, new, level, words):
    found = schema_changes(old, new)
    assert worst(found) is level and (not words or any(words in c.what for c in found))


def test_classes_and_branches_that_go_or_come_are_changes():
    one = {"title": "Deck", "properties": {}, "$defs": {"Card": {"title": "Card"}}}
    two = {"title": "Deck", "properties": {}, "$defs": {"Card": {"title": "Card"}, "Mark": {"title": "Mark"}}}
    assert schema_changes(one, two) == [Change(Level.COMPATIBLE, "Mark", "added to the model")]
    assert schema_changes(two, one) == [Change(Level.BREAKING, "Mark", "no longer part of the model")]

    def items(*refs: str) -> dict[str, object]:
        return {"properties": {"content": {"items": {"oneOf": [{"$ref": r} for r in refs]}}}, "title": "Deck"}

    assert worst(schema_changes(items("a", "b"), items("a"))) is Level.BREAKING
    assert worst(schema_changes(items("a"), items("a", "b"))) is Level.COMPATIBLE
    assert schema_changes(items("a"), items("a")) == []
    plain = {"title": "Deck", "properties": {"tags": {"items": {"type": "string", "maxLength": 9}}}}
    tighter = {"title": "Deck", "properties": {"tags": {"items": {"type": "string", "maxLength": 5}}}}
    assert [c.what for c in schema_changes(plain, tighter)] == ["maxLength 9 -> 5"]


def test_the_schemas_texmodel_writes_are_classified():
    """Two releases of one model, as `json_schema` writes them: a rename with `renamed_from` keeps old data, a new
    optional field is an addition, a field that went breaks old data."""
    before, after = Package("acme-before", prefix="ab"), Package("acme-after", prefix="ab")

    @before.command
    class Line(Command):  # pyright: ignore[reportRedeclaration]
        """A line."""

        text: Text
        gone: Text | None = None
        body = "#text #gone"

    old = json_schema(Line)

    @after.command
    class Line(Command):
        """A line."""

        words: Text = field(renamed_from="text")
        note: Text | None = None
        body = "#words #note"

    found = {(c.where, c.level) for c in schema_changes(old, json_schema(Line))}
    assert found == {
        ("Line.text", Level.COMPATIBLE),
        ("Line.note", Level.COMPATIBLE),
        ("Line.gone", Level.BREAKING),
    }
