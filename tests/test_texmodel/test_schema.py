"""Package-level schema and renamed fields (§21a 15)."""

import json
from typing import Any

import jsonschema
import pytest
from typer.testing import CliRunner

from texmodel import cli
from texmodel.components import Command, Environment, Value, field
from texmodel.package import Package
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import Length, Text

pkg = Package("schema-demo", prefix="sc")


@pkg.value
class Gap(Value[Length]):
    """Space under a fact."""

    default = Length("2mm")


@pkg.value
class Shown(Value[bool]):
    """A flag."""

    default = True


@pkg.command
class Fact(Command):
    """One fact."""

    body = "#text #note"
    text: Text = field(renamed_from="body")
    note: Text | None = field(renamed_from="remark", default=None)


@pkg.environment
class Card(Environment):
    """A card."""

    children = [Fact.times(3)]
    begin = r"\begin{center}#title"
    end = r"\end{center}"
    title: Text = field(renamed_from="name")


def test_an_old_key_loads_and_the_new_key_is_written():
    old = {"name": "Fox", "content": [{"type": "Fact", "body": "a", "remark": "n"}, {"type": "Fact", "text": "b"}]}
    card = from_dict(Card, old)
    assert card == Card(Fact("a", note="n"), Fact("b"), title="Fox")
    assert to_dict(card) == {
        "type": "Card",
        "title": "Fox",
        "content": [{"type": "Fact", "text": "a", "note": "n"}, {"type": "Fact", "text": "b"}],
    }
    assert from_dict(Fact, {"body": "x"}) == Fact("x")
    assert from_dict(Card, to_dict(card)) == card


def test_giving_both_the_old_and_the_new_key_is_reported_by_path():
    with pytest.raises(ExceptionGroup) as group:
        from_dict(Card, {"title": "a", "name": "b", "content": [{"type": "Fact", "text": "x", "body": "y"}]})
    messages = [str(e) for e in group.value.exceptions]
    assert any("'title' and its old name 'name' are both given" in m for m in messages)
    with pytest.raises(ExceptionGroup, match="invalid Fact"):
        from_dict(Fact, {"text": "x", "body": "y"})


def test_the_schema_records_the_old_name_of_a_renamed_field():
    assert json_schema(Fact)["properties"]["text"]["x-renamed-from"] == "body"
    card = json_schema(Card)
    assert card["properties"]["title"]["x-renamed-from"] == "name"
    assert card["$defs"]["Fact"]["properties"]["note"]["x-renamed-from"] == "remark"


def test_a_package_schema_has_every_component_and_value_and_validates_data():
    schema = json_schema(pkg)
    assert schema["title"] == "schema-demo" and set(schema["$defs"]) == {
        "Fact",
        "Card",
        "Comment",
        "Value.Gap",
        "Value.Shown",
    }  # Card accepts a bare Comment
    assert schema["$defs"]["Value.Gap"] == {"title": "Gap", "description": "Space under a fact.", "type": "string"}
    assert schema["$defs"]["Value.Shown"]["type"] == "boolean"
    assert schema["$defs"]["Fact"]["properties"]["text"]["x-renamed-from"] == "body"
    jsonschema.Draft202012Validator.check_schema(schema)
    card = jsonschema.Draft202012Validator(schema | {"$ref": "#/$defs/Card"})
    good: dict[str, Any] = dict(to_dict(Card(Fact("a"), title="Fox")))
    assert list(card.iter_errors(good)) == []
    assert list(card.iter_errors({**good, "title": 3}))
    assert list(card.iter_errors({"content": []}))  # title is required


def test_texmodel_schema_writes_the_package_schema(tmp_path, monkeypatch):
    (tmp_path / "schemamod.py").write_text("from test_texmodel.test_schema import pkg\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.texmodel]\nprefix = "sc"\npackage = "test_texmodel.test_schema:pkg"\nschema_output = "out/schema.json"\n'
    )
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.app, ["schema"])
    assert result.exit_code == 0 and "wrote out/schema.json" in result.stdout
    assert json.loads((tmp_path / "out" / "schema.json").read_text()) == json_schema(pkg)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.texmodel]\nprefix = "sc"\npackage = "test_texmodel.test_schema:pkg"\n'
    )
    assert "TM-D033" in CliRunner().invoke(cli.app, ["schema"]).stderr
