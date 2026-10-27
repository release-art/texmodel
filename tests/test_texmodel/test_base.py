"""A package that knows its base (§21): lookup, data, schema and `.sty` go through it; its own names win."""

import pytest

from texmodel.components import Command, Environment, Value
from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.package import Package
from texmodel.preamble import PreambleSlots
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import Length, Raw, Text

brand = Package("acme-brand", prefix="ac")
series = Package("acme-series", prefix="as", base=brand)


@brand.value
class Gap(Value[Length]):
    """The gap."""

    default = Length("2mm")


@brand.value
class Pad(Value[Length]):
    """The padding."""

    default = Length("1mm")


@brand.command
class Fact(Command):
    """A fact."""

    text: Text
    body = r"\par #text\par"


@brand.environment
class Card(Environment):
    """A card."""

    children = [Fact.times.any()]
    begin = r"\begin{center}"
    end = r"\end{center}"


def _override() -> None:
    @series.value
    class Pad(Value[Length]):  # the series' own Pad replaces the brand's
        """The series padding."""

        default = Length("3mm")


_override()


def test_the_base_is_kept_and_loaded_first():
    assert series.base is brand and brand.base is None
    assert series.require_entries()[0] == ("acme-brand", ())
    assert r"\RequirePackage{acme-brand}" in series.render()


def test_values_resolve_through_the_base_and_the_derived_package_wins():
    assert series.value_named("Gap") is Gap
    assert series.value_named("Pad") is not brand.value_named("Pad") is not None
    assert series.value_named("Pad").__doc__ == "The series padding."
    assert series.value_named("Nope") is None
    assert series.value_named("Fact") is None  # a command is not a value


def test_data_names_a_base_value_and_a_base_node():
    data = {
        "settings": [{"type": "Gap", "value": "3mm"}, {"type": "Pad", "value": "4mm"}],
        "content": [{"type": "Card", "content": [{"type": "Fact", "text": "a"}]}],
    }
    doc = from_dict(series, data)
    assert type(doc.settings[0]) is Gap and type(doc.settings[1]) is series.value_named("Pad")
    assert to_dict(doc) == {"type": "Document", **data}
    assert r"\setlength{\acGap}{3mm}" in series.document(doc)


def test_the_schema_covers_the_base():
    schema = json_schema(series)
    assert {"Card", "Fact", "GapSetting", "Value.Gap"} <= set(schema["$defs"])
    assert schema["$defs"]["Value.Pad"]["description"] == "The series padding."


def test_a_base_name_in_a_slot_is_declared():
    own = Package("same-prefix", prefix="ac", base=brand)
    slots = PreambleSlots(after_package=(Raw(r"\renewcommand{\acFact}[1]{#1}"),))
    own.document(Document(preamble=slots))  # the base declares \acFact
    with pytest.raises(ExceptionGroup):
        Package("other", prefix="ac").document(Document(preamble=slots))


def test_a_base_must_not_be_builtin():
    kernel = Package("latex", prefix="", builtin=True)
    with pytest.raises(DeclarationError, match="always loaded"):
        Package("x", prefix="x", base=kernel)
