"""A `Document` as data (D1a, §21): settings, options and preamble round-trip and are in the schema and the plan."""

from typing import Any

import jsonschema
import pytest

from texmodel.body import Comment
from texmodel.components import Command, Environment, Passthrough, Value
from texmodel.document import Document
from texmodel.package import Package
from texmodel.plan import EditKind, Plan
from texmodel.preamble import (
    GraphicsPath,
    InputIfExists,
    InputPath,
    PassOption,
    PdfInfo,
    PreambleSlots,
    RequireMetadata,
)
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import CMYK, Colour, Length, Raw, Text

pkg = Package("deck-data", prefix="dd")


@pkg.value
class Gap(Value[Length]):
    """The gap."""

    default = Length("2mm")


@pkg.value
class Ink(Value[Colour]):
    """The ink."""

    default = CMYK(0, 0, 0, 1)


@pkg.value
class Draft(Value[bool]):
    """Draft."""

    default = False


@pkg.value
class Footer(Value[Raw]):
    """The footer."""

    default = Raw("x")


@pkg.value
class Title(Value[Text]):
    """The title."""

    default = "Deck"


@pkg.command
class Fact(Command):
    """A fact."""

    text: Text
    body = r"\par #text"


@pkg.environment
class Card(Environment):
    """A card."""

    children = [Fact.times.any(), Passthrough.times.any()]
    begin = r"\begin{center}"
    end = r"\end{center}"


SLOTS = PreambleSlots(
    before_class=(RequireMetadata(lang="en-GB"), PassOption("xcolor", "table")),
    before_package=(InputPath("res/", "more/"), InputIfExists("options")),
    after_package=(GraphicsPath("img/", include_cwd=False), PdfInfo(Title="Rex & co"), Raw(r"\relax")),
)


def full() -> Document:
    return Document(
        Comment("start"),
        Card(Fact(text="a"), Passthrough(Raw(r"\vspace{1mm}"))),
        options=["a4paper", "11pt"],
        settings=[Gap(Length("3mm")), Ink(CMYK(0, 0.5, 1, 0)), Draft(True), Title("A & B"), Footer(Raw(r"\textbf{f}"))],
        preamble=SLOTS,
    )


def test_a_document_round_trips_through_data():
    data: dict[str, Any] = dict(to_dict(full()))
    assert data["options"] == ["a4paper", "11pt"]
    assert data["settings"][:2] == [
        {"type": "Gap", "value": "3mm"},
        {"type": "Ink", "value": {"c": 0.0, "m": 0.5, "y": 1.0, "k": 0.0}},
    ]
    assert data["preamble"]["after_package"][:2] == [
        {"type": "GraphicsPath", "dirs": ["img/"], "include_cwd": False},
        {"type": "PdfInfo", "entries": {"Title": "Rex & co"}},
    ]
    loaded = from_dict(pkg, data)
    assert isinstance(loaded, Document)
    assert to_dict(loaded) == data
    assert pkg.plan(loaded) == pkg.plan(full())
    assert loaded.preamble == SLOTS


def test_an_empty_document_writes_only_its_content():
    assert to_dict(Document(Card())) == {"type": "Document", "content": [{"type": "Card", "content": []}]}
    assert to_dict(from_dict(pkg, {})) == {"type": "Document", "content": []}


def test_the_plan_names_every_line_of_a_loaded_document():
    plan = pkg.plan(from_dict(pkg, to_dict(full())))  # pyright: ignore[reportArgumentType]
    paths = [x.path for x in plan.lines]
    assert paths.count("settings[0]") == paths.count("settings[4]") == 1
    assert "preamble.before_class[1]" in paths and "preamble.after_package[2]" in paths
    assert plan.lines[next(i for i, x in enumerate(plan.lines) if x.path == "Card[1]")].path == "Card[1]"


def test_a_hand_edit_of_a_setting_or_a_preamble_line_is_found_by_path():
    plan = pkg.plan(full())
    text = plan.text.replace(r"\setlength{\ddGap}{3mm}", r"\setlength{\ddGap}{9mm}").replace(r"\relax", r"\relax\relax")
    found = {e.path: e.kind for e in Plan.from_json(plan.to_json()).edits(text)}
    assert found == {"settings[0]": EditKind.CHANGED, "preamble.after_package[2]": EditKind.CHANGED}


def test_an_entry_in_the_wrong_slot_is_still_tm_c008():
    data = {"preamble": {"before_class": [{"type": "GraphicsPath", "dirs": ["img/"]}]}}
    loaded = from_dict(pkg, data)
    with pytest.raises(ExceptionGroup) as group:
        pkg.document(loaded)  # pyright: ignore[reportArgumentType]
    (error,) = group.value.exceptions
    assert (error.code, error.path) == ("TM-C008", "preamble.before_class[0]")  # pyright: ignore[reportAttributeAccessIssue]


def paths(group: pytest.ExceptionInfo[ExceptionGroup[Exception]]) -> list[tuple[str, str]]:
    return [(e.code, e.path) for e in group.value.exceptions]  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"options": ["a4paper", "a]b"]}, [("TM-C020", "options[1]")]),
        ({"settings": [{"type": "Nope", "value": 1}]}, [("TM-C020", "settings[0]")]),
        ({"settings": [{"type": "Gap", "value": 3.5}]}, [("TM-C020", "settings[0].value")]),
        ({"settings": [{"type": "Draft"}]}, [("TM-C020", "settings[0].value")]),
        (
            {"preamble": {"after_package": [{"type": "PdfInfo", "entries": {"a b": "x"}}]}},
            [("TM-C020", "preamble.after_package[0]")],
        ),
        ({"preamble": {"after_package": ["{"]}}, [("TM-C020", "preamble.after_package[0]")]),
        ({"preamble": {"after_package": [{"type": "Nope"}]}}, [("TM-C020", "preamble.after_package[0]")]),
        ({"preamble": {"middle": []}}, [("TM-C020", "preamble.middle")]),
        (
            {"preamble": {"before_package": [{"type": "InputPath", "dirs": "res/"}]}},
            [("TM-C020", "preamble.before_package[0].dirs")],
        ),
        ({"content": [{"type": "Nope"}]}, [("TM-C020", "content[0]")]),
        ({"content": [{"type": "Fact"}]}, [("TM-C020", "Fact[0].text")]),
        (
            {"content": [{"type": "Card", "content": [{"type": "Fact", "text": 3}]}]},
            [("TM-C020", "Card[0]/Fact[0].text")],
        ),
        ({"colour": "red"}, [("TM-C020", "colour")]),
    ],
)
def test_everything_wrong_comes_at_once_with_the_path_the_plan_uses(data, expected):
    with pytest.raises(ExceptionGroup) as group:
        from_dict(pkg, data)
    assert paths(group) == expected


def test_all_errors_of_a_document_are_reported_together():
    with pytest.raises(ExceptionGroup) as group:
        from_dict(pkg, {"options": ["a]b"], "settings": [{"type": "Gap", "value": 1.5}], "content": [{"type": "Fact"}]})
    assert len(group.value.exceptions) == 3


def test_a_package_with_no_values_takes_no_settings():
    bare = Package("bare-data", prefix="bd")
    assert from_dict(bare, {"options": ["a4paper"]}).options == ("a4paper",)  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(ExceptionGroup):
        from_dict(bare, {"settings": []})


def test_a_package_with_one_value_takes_its_settings():
    one = Package("one-data", prefix="od")

    @one.value
    class Only(Value[bool]):
        """The one."""

        default = True

    loaded = from_dict(one, {"settings": [{"type": "Only", "value": False}]})
    assert [(type(v).__name__, v.value) for v in loaded.settings] == [("Only", False)]  # pyright: ignore[reportAttributeAccessIssue]


def test_the_schema_describes_the_document_and_checks_data():
    schema = json_schema(pkg)
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["$ref"] == "#/$defs/Document"
    assert {"GapSetting", "PdfInfoEntry", "PreambleData", "Card", "Passthrough"} <= set(schema["$defs"])
    assert set(schema["$defs"]["Document"]["properties"]) == {"type", "options", "settings", "preamble", "content"}
    validator = jsonschema.Draft202012Validator(schema)
    assert list(validator.iter_errors(dict[str, Any](to_dict(full())))) == []
    assert list(validator.iter_errors({"options": ["a]b"]}))
    assert list(validator.iter_errors({"settings": [{"type": "Gap", "value": 3}]}))
    assert list(validator.iter_errors({"preamble": {"after_package": [{"type": "PdfInfo", "entries": {"a": 1}}]}}))
    assert list(validator.iter_errors({"colour": "red"}))


def test_a_document_is_given_alone_or_as_bare_nodes():
    with pytest.raises(TypeError, match="alone"):
        pkg.plan(Document(Card()), Card())
    assert pkg.document(Card(), Card()) == pkg.document(Document(Card(), Card()))


def test_test_document_keeps_what_the_document_carries():
    tex = pkg.test_document(Document(Card(), options=["a4paper"], settings=[Draft(True)], preamble=SLOTS), stub=[Fact])
    assert r"\documentclass[a4paper]{article}" in tex and r"\ddDrafttrue" in tex and r"\relax" in tex
