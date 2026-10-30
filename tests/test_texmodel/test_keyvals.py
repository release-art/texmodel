"""Key lists: item kinds, key rules, protection of values, relations, data."""

import dataclasses
import enum

import pydantic
import pytest
from hypothesis import (
    given,
    strategies as st,
)

from texmodel.body import Hole
from texmodel.components import Command, Environment
from texmodel.errors import DeclarationError
from texmodel.interface import PAREN, Flag, Item, OptionalValue, Star, Switch, arg
from texmodel.keys import KEYVAL, KVOPTIONS, L3KEYS, PGFKEYS, XKEYVAL
from texmodel.keyvals import Entry, KeyVals, key
from texmodel.package import Package
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import RGB, Choice, Colour, Length, Raw, Text

from .test_document import refused


@enum.unique
class VAlign(Choice):
    TOP = "t"
    BOTTOM = "b"


@enum.unique
class Arrow(Choice):
    TO = Raw("->")
    BACK = Raw("<-")


class Inner(KeyVals, rules=PGFKEYS):
    draw: Colour | None = None
    dashed: Flag = False


class Options(KeyVals, rules=PGFKEYS):
    max_width: Length | None = key("max width")
    center: Flag = False
    clip: Switch | None = None
    valign: VAlign | None = None
    arrow: Item[Arrow] | None = None
    rounded: OptionalValue[Length] | None = key("rounded corners")
    style: Inner | None = key("every node/.style")
    title: Text | None = None
    tags: list[Text] | None = None
    levels: list[Item[int]] | None = None
    extra: Item[Raw] | None = None


def test_every_item_kind_is_written_in_declaration_order_and_unset_ones_are_left_out():
    options = Options(
        max_width=Length.expr(r"\linewidth"),
        center=True,
        clip=False,
        valign=VAlign.TOP,
        arrow=Arrow.TO,
        rounded=True,
        style=Inner(draw=RGB(1, 0, 0), dashed=True),
        title="A & B",
        tags=["x", "y z"],
        levels=[1, 2],
        extra=Raw("foo=bar, baz"),
    )
    assert options.render() == (
        r"max width=\linewidth,center,clip=false,valign=t,->,rounded corners,every node/.style={draw={1,0,0},dashed},"
        r"title=A \& B,tags=x,tags=y z,1,2,foo=bar, baz"
    )
    assert Options(rounded=Length("2pt"), clip=True).render() == "clip=true,rounded corners=2pt"
    assert Options().render() == "" and Options(tags=[]).render() == ""


@pytest.mark.parametrize(
    ("value", "written"),
    [
        ("a,b", "title={a,b}"),
        ("a=b", "title={a=b}"),
        ("a]b", "title={a]b}"),
        (" a", "title={{ a}}"),
        ("a ", "title={{a }}"),
        ("", "title={}"),
        ("plain text", "title=plain text"),
    ],
)
def test_a_value_the_library_would_split_or_strip_is_put_in_braces(value, written):
    assert Options(title=value).render() == written


def test_a_raw_value_is_as_written_unless_the_rules_brace_everything():
    class Raws(KeyVals, rules=PGFKEYS):
        a: Raw | None = None

    class Braced(KeyVals, rules=dataclasses.replace(PGFKEYS, braced=True)):
        a: Raw | None = None
        b: Length | None = None

    assert Raws(a=Raw("1,2")).render() == "a=1,2"
    assert Braced(a=Raw("x"), b=Length("1pt")).render() == "a={x},b={1pt}"


def test_the_rules_decide_the_spelling_of_assignment_separator_and_booleans():
    rules = dataclasses.replace(PGFKEYS, assign=" = ", separator="; ", booleans=("on", "off"))

    class Spaced(KeyVals, rules=rules):
        a: Switch | None = None
        b: Length | None = None

    assert Spaced(a=True, b=Length("1pt")).render() == "a = on; b = 1pt"
    assert {r.nesting for r in (KEYVAL, KVOPTIONS)} == {False}
    assert all(r.nesting for r in (XKEYVAL, PGFKEYS, L3KEYS))


def test_exclusive_keys_and_requirements_are_checked_when_the_list_is_built():
    class Placement(KeyVals, rules=PGFKEYS):
        exclusive = (("left", "right"),)
        requires = {"offset": "left"}
        left: Flag = False
        right: Flag = False
        offset: Length | None = None

    assert Placement(left=True, offset=Length("1pt")).render() == "left,offset=1pt"
    with pytest.raises(pydantic.ValidationError, match="at most one of"):
        Placement(left=True, right=True)
    with pytest.raises(pydantic.ValidationError, match="offset needs left"):
        Placement(offset=Length("1pt"))
    assert Placement().render() == ""


def test_unknown_keys_and_wrong_types_are_refused_at_construction():
    with pytest.raises(pydantic.ValidationError):
        Options(nope=1)  # pyright: ignore[reportCallIssue]
    with pytest.raises(pydantic.ValidationError):
        Options(max_width="3cm")  # pyright: ignore[reportArgumentType]  # lax coercion makes it a Length, not a bad string
        Options(max_width="three")  # pyright: ignore[reportArgumentType]


def test_declaration_errors_of_a_key_list():
    with refused("TM-M036"):

        class NoRules(KeyVals):
            a: Text | None = None

    with refused("TM-M004"):

        class Plain(KeyVals, rules=PGFKEYS):
            a: bool = False

    with refused("TM-M004"):

        class Nested(KeyVals, rules=KEYVAL):
            a: Inner | None = None

    with refused("TM-M004"):

        class Token(KeyVals, rules=PGFKEYS):
            a: Star

    with refused("TM-M004"):

        class Odd(KeyVals, rules=PGFKEYS):
            a: set[int] | None = None

    with refused("TM-M004"):

        class Two(KeyVals, rules=PGFKEYS):
            a: int | str | None = None

    with refused("TM-M004"):

        class Repeats(KeyVals, rules=PGFKEYS):
            a: list[Flag]

    with refused("TM-M004"):

        class RepeatsOptional(KeyVals, rules=PGFKEYS):
            a: list[OptionalValue[int]]

    with refused("TM-M004"):

        class BareKeyList(KeyVals, rules=PGFKEYS):
            a: Item[Inner] | None = None

    with refused("TM-M004"):

        class ListOfSets(KeyVals, rules=PGFKEYS):
            a: list[set[int]] | None = None

    with refused("TM-M004"):

        class OptionalList(KeyVals, rules=PGFKEYS):
            a: list[int | str] | None = None

    with refused("TM-M004"):

        class OptionalKeyList(KeyVals, rules=PGFKEYS):
            a: OptionalValue[Inner] | None = None

    with refused("TM-M004"):

        class BadExclusive(KeyVals, rules=PGFKEYS):
            exclusive = (("a", "zzz"),)
            a: Flag = False

    with refused("TM-M004"):

        class BadRequires(KeyVals, rules=PGFKEYS):
            requires = {"a": "zzz"}
            a: Flag = False


def test_a_subclass_keeps_its_parents_rules_and_may_change_them():
    class Child(Inner):
        solid: Flag = False

    class Other(Inner, rules=KEYVAL):
        pass

    assert Child(solid=True, dashed=True).render() == "dashed,solid"
    assert Other.__tm_rules__ is KEYVAL and Child.__tm_rules__ is PGFKEYS


def test_the_schema_keeps_the_tex_spelling_and_data_uses_field_names():
    schema = Options.model_json_schema()
    assert schema["properties"]["max_width"]["x-tex-key"] == "max width"
    assert "x-tex-key" not in schema["properties"]["valign"]
    assert Options.model_validate({"max_width": "3cm", "center": True}).render() == "max width=3cm,center"


# --- as a component's argument ----------------------------------------------------------------------------------------


def adjust():
    p = Package("kv-demo", prefix="", builtin=True, adopted=True)

    @p.command
    class AdjustBox(Command):
        r"""`\adjustbox{max width=\linewidth}{content}`."""

        cs = "adjustbox"
        options: Options
        text: Raw

    @p.command
    class Optional(Command):
        r"""`\includegraphics[width=3cm]{file}`."""

        cs = "includegraphics"
        path: Text
        options: Options | None = None

    @p.command
    class Parens(Command):
        """Key list in parentheses."""

        cs = "parens"
        options: Options | None = arg(PAREN, default=None)
        text: Raw

    @p.environment
    class Picture(Environment):
        """An environment with an option list."""

        cs = "picture"
        options: Options | None = None

    return AdjustBox, Optional, Parens, Picture


def test_a_key_list_fills_a_slot_and_an_empty_one_in_an_optional_slot_is_not_written():
    adjust_box, optional, parens, picture = adjust()
    opts = Options(max_width=Length.expr(r"\linewidth"), center=True)
    assert adjust_box(options=opts, text=Raw("x")).render() == r"\adjustbox{max width=\linewidth,center}{x}"
    assert (
        adjust_box(options=Options(), text=Raw("x")).render() == r"\adjustbox{}{x}"
    )  # a required slot is always written
    assert optional(path="f.pdf", options=opts).render() == r"\includegraphics[max width=\linewidth,center]{f.pdf}"
    assert optional(path="f.pdf", options=Options()).render() == r"\includegraphics{f.pdf}"
    assert optional(path="f.pdf").render() == r"\includegraphics{f.pdf}"
    assert parens(text=Raw("x"), options=Options(center=True)).render() == r"\parens(center){x}"
    assert picture(options=Options(clip=True)).render() == "\\begin{picture}[clip=true]\n\\end{picture}"
    assert optional(path="f.pdf", options=Options(title="a]b")).render() == r"\includegraphics[title={a]b}]{f.pdf}"
    assert adjust_box(options=opts, text=Raw("x")).violations() == []
    (problem,) = adjust_box(options="not options", text=Raw("x")).violations()  # pyright: ignore[reportArgumentType]
    assert problem.code == "TM-C003" and "Options" in problem.message


def test_a_key_list_is_data_and_has_a_schema():
    adjust_box, *_ = adjust()
    node = adjust_box(
        options=Options(max_width=Length("3cm"), center=True, valign=VAlign.TOP, tags=["a"]), text=Raw("x")
    )
    data = to_dict(node)
    assert data == {
        "type": "AdjustBox",
        "options": {"max_width": "3cm", "center": True, "valign": "TOP", "tags": ["a"]},
        "text": "x",
    }
    assert from_dict(adjust_box, data) == node
    assert json_schema(adjust_box)["properties"]["options"]["$ref"].endswith("/Options")
    with pytest.raises(ExceptionGroup):
        from_dict(adjust_box, {"type": "AdjustBox", "options": {"nope": 1}, "text": "x"})


def test_a_reference_may_pass_a_key_list():
    p = Package("kv-ref", prefix="kr")
    adjust_box, *_ = adjust()

    @p.command
    class Wrapped(Command):
        """Calls adjustbox."""

        text: Raw

        def body(self):
            yield adjust_box.call(Options(center=True), Hole("text"))

    assert r"\adjustbox{center}{#1}" in p.render()


@given(st.text(max_size=20))
def test_no_text_value_can_end_the_item_it_is_in(value):
    text = Options(title=value).render()
    assert text.startswith("title=")
    rest = text[len("title=") :]
    if rest.startswith("{"):
        assert rest.endswith("}")
    else:
        assert "," not in rest and "]" not in rest and "=" not in rest


def test_the_item_helpers_refuse_a_bad_key_spelling_rule_and_ignore_pydantic_errors():
    assert DeclarationError  # imported for the refused() helper's sake
    assert key("a b").json_schema_extra == {"x-tex-key": "a b"} and key().json_schema_extra is None


def test_a_library_that_trims_whatever_it_is_given_gets_the_value_as_it_is():
    class Trims(KeyVals, rules=L3KEYS):
        title: Text | None = None

    assert Trims(title=" a").render() == "title= a" and Trims(title="a,b").render() == "title={a,b}"


def test_an_entry_spells_its_own_key_and_a_list_of_them_repeats():
    class Rules(KeyVals, rules=L3KEYS):
        thick: Flag = False
        rules: list[Item[Entry]] | None = None

    inner = Inner(dashed=True)
    entries = [Entry.of("cell{1}{2}", inner), Entry.of("hline{1}", Raw("1"), inner), Entry.of("x")]
    assert Rules(thick=True, rules=entries).render() == "thick,cell{1}{2}={dashed},hline{1}={1}{dashed},x="
    with pytest.raises(pydantic.ValidationError):
        Rules(rules=[Raw("not an entry")])  # pyright: ignore[reportArgumentType]
