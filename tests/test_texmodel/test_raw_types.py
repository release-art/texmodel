"""`Macro` and `FilePath`: TeX a field can hold where a bare `Raw` is too loose."""

from pathlib import PurePosixPath

import pydantic
import pytest

from texmodel.errors import ValidationError
from texmodel.std.graphicx import IncludeGraphics, IncludeGraphicsOptions
from texmodel.types import ControlSequence, FilePath, FontName, Length, Macro, Name, NameList, Raw


@pytest.mark.parametrize("tex", [r"\jobname", r"\figdir{a}", r"\pic{a}{b{c}}", r"\a@b", r"\a{50\%}"])
def test_a_macro_is_a_control_word_and_braced_arguments(tex):
    assert Macro(tex).tex == tex


@pytest.mark.parametrize("tex", ["jobname", r"\jobname-fig", r"\a b", r"\a{b}c", r"\a{b", "", r"\ "])
def test_anything_else_is_refused_as_a_macro(tex):
    with pytest.raises(ValidationError) as raised:
        Macro(tex)
    assert raised.value.code in {"TM-C007", "TM-C029"}


def test_a_file_name_is_written_as_it_is():
    assert FilePath("img/a_b~c d.png").tex == "img/a_b~c d.png"
    assert FilePath.of(PurePosixPath("img", "a.png")).tex == "img/a.png"


@pytest.mark.parametrize("name", ["a{b.png", "a}.png", r"a\b.png", "50%.png", "a#1.png", "a\n.png", ""])
def test_what_tex_reads_as_syntax_is_refused_in_a_file_name(name):
    with pytest.raises(ValidationError) as raised:
        FilePath(name)
    assert raised.value.code == "TM-C028"


def test_a_picture_takes_a_file_name_a_macro_or_raw_tex():
    sized = IncludeGraphicsOptions(width=Length("2cm"))
    assert IncludeGraphics(path=FilePath("a.png"), options=sized).render() == r"\includegraphics[width=2cm]{a.png}"
    assert IncludeGraphics(path=Macro(r"\figdir{a}")).render() == r"\includegraphics{\figdir{a}}"
    assert IncludeGraphics(path=Raw(r"\jobname-fig")).render() == r"\includegraphics{\jobname-fig}"


def test_data_loads_a_typed_field_through_its_check():
    class Holder(pydantic.BaseModel):
        file: FilePath
        call: Macro

    ok = Holder.model_validate({"file": "a/b.png", "call": r"\x{y}"})
    assert ok.file == FilePath("a/b.png") and ok.model_dump(mode="json") == {"file": "a/b.png", "call": r"\x{y}"}
    with pytest.raises(pydantic.ValidationError):
        Holder.model_validate({"file": "a%.png", "call": r"\x"})


@pytest.mark.parametrize(
    ("cls", "good", "bad", "code"),
    [
        (ControlSequence, r"\mylen", ["mylen", r"\a{b}", r"\a b", ""], "TM-C030"),
        (Name, "tmc", ["1a", "a b", r"\a", ""], "TM-C031"),
        (Name, "arrows.meta", ["a,b"], "TM-C031"),
        (NameList, "skins, breakable", ["a,", ",a", "a b", ""], "TM-C032"),
        (FontName, "Latin Modern Roman", ["a}", "50%", ""], "TM-C028"),
    ],
)
def test_a_checked_name_accepts_its_form_and_refuses_the_rest(cls, good, bad, code):
    assert cls(good).tex == good
    for tex in bad:
        with pytest.raises(ValidationError) as raised:
            cls(tex)
        assert raised.value.code == code


def test_a_field_of_a_header_refuses_the_wrong_kind_of_name():
    from texmodel.std.latex import SetLength

    assert SetLength(length=ControlSequence(r"\x"), value=Length("1mm")).render() == r"\setlength{\x}{1mm}"
    assert SetLength(length=Raw("2cm"), value=Length("1mm")).violations()  # pyright: ignore[reportArgumentType]
