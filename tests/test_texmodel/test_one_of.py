"""A field of several kinds (`Icon | Picture`), and a type that is a value because it writes itself (`AsTeX`)."""

import dataclasses
import enum

import pytest

from texmodel._internal.read import detokenized
from texmodel.components import Command
from texmodel.errors import DeclarationError, ValidationError
from texmodel.ext.graphics import Picture
from texmodel.interface import AsTeX
from texmodel.package import Package
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.testing import Call, read_call
from texmodel.types import Choice, FilePath, Raw, Text


@enum.unique
class Icon(Choice):
    RULER = Raw(r"\acRuler")
    PAW = "paw"


pkg = Package("one-of-demo", prefix="oo")


@pkg.command
class Row(Command):
    """A row."""

    body = "#icon #label"
    icon: Icon | Picture | None = None
    label: Text


@pkg.command
class Mark(Command):
    """A mark."""

    body = "#mark"
    mark: Icon | int


@pkg.command
class Where(Command):
    """Where."""

    body = "#where"
    where: Icon | FilePath


@dataclasses.dataclass(frozen=True)
class Stamp(AsTeX):
    name: str

    def render(self) -> str:
        return rf"\stamp{{{self.name}}}"


@pkg.command
class Stamped(Command):
    """A stamped line."""

    body = "#stamp"
    stamp: Stamp | Text


def test_a_field_writes_the_alternative_that_holds_the_value():
    assert Row(icon=Icon.RULER, label="Size").render() == r"\ooRow[\acRuler]{Size}"
    assert Row(icon=Icon.PAW, label="Size").render() == r"\ooRow[paw]{Size}"
    picture = Row(icon=Picture("img/crest.png", alt="Crest"), label="Breed")
    assert picture.render() == r"\ooRow[{\includegraphics[alt=Crest]{img/crest.png}}]{Breed}"
    assert Row(label="Empty").render() == r"\ooRow{Empty}"
    assert Mark(mark=3).render() == r"\ooMark{3}"


def test_a_value_of_no_alternative_is_refused_naming_them():
    (bad,) = Row(icon="Ruler", label="x").violations()  # type: ignore[arg-type]
    assert bad.code == "TM-C003" and "one of ['RULER', 'PAW'] | Picture" in bad.message
    assert Row(icon=Picture("a.png", decorative=True), label="x").violations() == []


def test_a_union_with_a_kind_no_field_takes_is_still_refused():
    with pytest.raises(DeclarationError) as caught:

        class Odd(Command):
            """Odd."""

            body = "#x"
            x: Icon | dict[str, str]

    assert caught.value.code == "TM-M004"


def test_a_type_with_a_render_that_does_not_opt_in_is_refused():
    class Quiet:
        def render(self) -> str:
            return "x"

    with pytest.raises(DeclarationError) as caught:

        class Odd(Command):
            """Odd."""

            body = "#x"
            x: Quiet

    assert caught.value.code == "TM-M004"


def test_any_type_that_subclasses_astex_is_a_value():
    assert Stamped(stamp=Stamp("a")).render() == r"\ooStamped{\stamp{a}}"
    assert Stamped(stamp="plain").render() == r"\ooStamped{plain}"


def test_data_names_a_member_or_gives_the_picture_and_the_picture_checks_itself():
    assert from_dict(Row, {"icon": "PAW", "label": "a"}) == Row(icon=Icon.PAW, label="a")
    data = {"icon": {"path": "x.png", "alt": "X"}, "label": "a"}
    loaded = from_dict(Row, data)
    assert loaded.render() == r"\ooRow[{\includegraphics[alt=X]{x.png}}]{a}"
    icon = to_dict(loaded)["icon"]
    assert isinstance(icon, dict) and icon["path"] == "x.png"
    assert from_dict(Row, to_dict(loaded)) == loaded
    for icon in ({"path": "x.png"}, "Ruler"):
        with pytest.raises((ExceptionGroup, ValidationError)):
            from_dict(Row, {"icon": icon, "label": "a"})


def test_the_schema_offers_each_alternative():
    icon = json_schema(Row)["properties"]["icon"]
    assert [m.get("enum") or m.get("$ref") or m["type"] for m in icon["anyOf"]] == [
        ["RULER", "PAW"],
        "#/$defs/Picture",
        "null",
    ]
    assert "Picture" in json_schema(Row)["$defs"]


def test_a_stub_call_reads_back_what_it_can():
    (icon, _) = read_call(Row, Call("ooRow", (r"\acRuler", "x")))
    assert icon.value is Icon.RULER
    (paw, _) = read_call(Row, Call("ooRow", ("paw", "x")))
    assert paw.value is Icon.PAW
    crest = Picture("img/crest.png", alt="Crest")
    for shown in (detokenized(crest.render()), "{" + detokenized(crest.render()) + "}"):
        (picture, _) = read_call(Row, Call("ooRow", (shown, "x")))
        assert picture.value == crest  # a hand edit of the picture is seen
    (unread,) = read_call(Stamped, Call("ooStamped", (r"\stamp{a}",)))
    assert unread.value is None and unread.violation is None  # a type that does not read leaves the field unread
    (number,) = read_call(Mark, Call("ooMark", ("7",)))
    assert number.value == 7
    (bad,) = read_call(Mark, Call("ooMark", ("seven",)))
    assert bad.violation and bad.violation.code == "TM-C021" and "not a Icon and" in bad.violation.message


def test_a_path_unions_with_a_choice():
    assert Where(where=FilePath("a/b.png")).render() == r"\ooWhere{a/b.png}"


def test_astex_is_abstract_until_a_type_writes_and_reads_itself():
    with pytest.raises(NotImplementedError):
        AsTeX().render()
    with pytest.raises(NotImplementedError):
        Stamp.read("x")
