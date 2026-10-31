"""A table for a block of rows (an icon, a label, a value): no header, flush edges, a colour a macro names, and a format
of the project's own."""

import dataclasses
import os
import re
from typing import Annotated

import pydantic
import pytest
from test_std.test_headers import compile_sample, host_compiler
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.components import Command, Value
from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.ext.table import Col, Format, Look, Rules, Table
from texmodel.interface import ColourName
from texmodel.package import Package
from texmodel.preamble import PreambleSlots
from texmodel.spec import from_dict
from texmodel.std import (
    latex,
    tabularray as t,
)
from texmodel.types import Length, Raw, Text, escape


@dataclasses.dataclass(frozen=True)
class Glyph(Format):
    """A glyph of the project's vocabulary, set in sans; a format of a project's own."""

    align = t.HAlign.CENTRE

    def _tex(self, value: object) -> str:
        return rf"\textsf{{{escape(str(value))}}}"


class Profile(pydantic.BaseModel):
    icon: Annotated[str, Col("", fmt=Glyph(), width=Length("6mm"))]
    label: Annotated[str, Col("", cells=t.CellSpec(fg=ColourName.macro(r"\bbRowLabelColour")))]
    value: Annotated[str, Col("", cells=t.CellSpec(font=Raw(r"\bfseries")))]


ROWS = [Profile(icon="a", label="Sound", value="Loud & clear"), Profile(icon="b", label="Spot", value="Near")]


def test_header_false_writes_no_header_row_and_no_rule_under_it():
    shown = Table(Profile, ROWS, header=False, look=Look.PLAIN).render()
    assert shown.splitlines()[1:3] == [r"\textsf{a} & Sound & Loud \& clear \\", r"\textsf{b} & Spot & Near \\"]
    assert "row{1}" not in shown and r"\bfseries" in shown  # only the value column's cell font
    booktabs = Table(Profile, ROWS, header=False).render()
    assert "hline{1}={wd=0.08em}" in booktabs and "hline{2}" not in booktabs and "hline{Z}={wd=0.08em}" in booktabs
    assert re.search(r"row\{[^}]*\}=\{font=\\bfseries", booktabs) is None
    assert "rowhead" not in Table(Profile, ROWS, header=False, long=True).render()


def test_an_empty_label_is_still_a_header_unless_it_is_switched_off():
    with_header = Table(Profile, ROWS).render()
    assert with_header.splitlines()[1] == " &  &  \\\\" and "row{1}={font=\\bfseries}" in with_header


def test_header_groups_need_a_header():
    class Grouped(pydantic.BaseModel):
        a: Annotated[str, Col("A", group="G")]

    assert Table(Grouped, [Grouped(a="x")]).render()
    with pytest.raises(DeclarationError) as raised:
        Table(Grouped, [Grouped(a="x")], header=False)
    assert raised.value.code == "TM-M083"


def test_a_totals_row_and_group_rows_keep_their_places_without_a_header():
    class Sold(pydantic.BaseModel):
        region: str
        city: Annotated[str, Col("City", stub=True)]
        n: Annotated[int, Col("N")]

    rows = [Sold(region="N", city="A", n=1), Sold(region="N", city="B", n=2)]
    from texmodel.ext.table import Total

    shown = Table(Sold, rows, header=False, group_by="region", totals=[Total("All", sum=("n",))]).render()
    lines = shown.splitlines()
    assert lines[1].startswith("N &") and lines[2].startswith("A &") and lines[-2].startswith("All &")


def test_a_macro_names_a_colour_that_is_read_when_the_document_is_typeset():
    macro = ColourName.macro(r"\bbRowLabelColour")
    assert macro == r"\bbRowLabelColour" and macro.names == () and ColourName.macro("bbX") == r"\bbX"
    assert ColourName(macro, tint=0.5) == r"\bbRowLabelColour!50" and ColourName(
        macro, tint=0.5, mix="white"
    ).names == ("white",)
    assert t.CellSpec(fg=macro).render() if hasattr(t.CellSpec(fg=macro), "render") else True
    assert r"cell{1-2}{2}={fg=\bbRowLabelColour}" in Table(Profile, ROWS, header=False).render()


def test_a_value_that_defines_the_macro_names_it_and_a_bad_macro_is_refused():
    pkg = Package("acme-profile", prefix="ap")

    @pkg.value
    class RowLabelColour(Value[Raw]):
        """The label colour, renewed by each series."""

        default = Raw("red!70")

    assert ColourName.macro(RowLabelColour) == r"\apRowLabelColour"
    for bad in (r"\two words", r"\x1", "", r"\\x"):
        with pytest.raises(DeclarationError) as raised:
            ColourName.macro(bad)
        assert raised.value.code == "TM-M067"

    class Loose(Value[Raw]):
        """Not registered."""

        default = Raw("x")

    with pytest.raises(DeclarationError) as raised:
        ColourName.macro(Loose)
    assert raised.value.code == "TM-M067"


def test_a_macro_colour_is_a_valid_argument_and_data_and_is_not_checked_against_the_package():
    pkg = Package("acme-label", prefix="al")

    @pkg.command
    class Tag(Command):
        """A coloured tag."""

        text: Text
        colour: ColourName
        body = r"\textcolor{#colour}{#text}"

    macro = ColourName.macro(r"\alTagColour")
    assert Tag(text="x", colour=macro).violations() == []
    assert Tag(text="x", colour=ColourName(macro, tint=0.5)).violations() == []
    assert [v.code for v in Tag(text="x", colour=ColourName("nonsense")).violations()] == ["TM-C022"]
    loaded = from_dict(pkg, {"content": [{"type": "Tag", "text": "x", "colour": r"\alTagColour!50"}]})
    assert loaded.content[0].colour == r"\alTagColour!50"  # pyright: ignore[reportAttributeAccessIssue]


def test_the_edges_are_flush_by_look_and_a_look_may_say_otherwise():
    flush = lambda look: Table(Profile, ROWS, header=False, look=look).render()  # noqa: E731
    assert "column{1}={leftsep=0pt}" in flush(Look.BOOKTABS) and "rightsep=0pt" in flush(Look.BOOKTABS)
    assert "leftsep" not in flush(Look.PLAIN) and "leftsep" not in flush(Look.GRID)  # their padding stays
    flat = flush(Look(rules=Rules.NONE))
    assert "column{1}={leftsep=0pt}" in flat and "column{3}={rightsep=0pt}" in flat and "hline" not in flat
    wide = flush(Look(rules=Rules.NONE, edge=Length("3pt")))
    assert "column{1}={leftsep=3pt}" in wide and "column{3}={rightsep=3pt}" in wide
    assert "leftsep" not in flush(Look(rules=Rules.NONE, edge=None))
    # `rules=` still wins, written last
    both = Table(Profile, ROWS, header=False, look=Look.PLAIN, rules=[t.column(1, t.ColumnSpec(leftsep=Length("1pt")))])
    assert both.render().count("leftsep") == 1 and "leftsep=1pt" in both.render()


def test_a_format_of_a_projects_own_writes_the_cells_and_sets_the_column():
    shown = Table(Profile, ROWS, header=False).render()
    assert r"\textsf{a} & Sound" in shown and "column{1}={halign=c,wd=6mm}" in shown
    assert Glyph().tex(None) == "–" and Glyph(missing="").tex(None) == "" and Glyph().tex("a&b") == r"\textsf{a\&b}"
    assert Glyph().numeric is False and Glyph.valign is None
    with pytest.raises(NotImplementedError):
        Format().tex("x")


@pytest.mark.tex
@pytest.mark.timeout(900)
async def test_real_tex_sets_the_profile_block_with_a_macro_colour(compiler, tmp_path):  # noqa: F811
    """No header, flush edges, a label colour read from a macro that is renewed after the package loads."""
    table = Table(Profile, ROWS, header=False, look=Look(rules=Rules.NONE))
    slots = PreambleSlots(
        after_package=(Raw(r"\newcommand{\bbRowLabelColour}{red}\renewcommand{\bbRowLabelColour}{blue}"),)
    )
    plan = t.package.plan(Document(table.node(), latex.Null(), preamble=slots))
    result, errors, gaps = await compile_sample(compiler, plan, tmp_path)
    if gaps and len(gaps) == len(errors):
        host = host_compiler() if os.environ.get("TEXMODEL_STD_ON_HOST") else None
        if host is None:
            pytest.skip(f"the reference image lacks: {sorted({d.message for d in gaps})}")
        result, errors, gaps = await compile_sample(host, plan, tmp_path / "host")
    assert result.ok and not errors, [(d.path, d.code, d.message) for d in errors]
    import pikepdf

    assert result.pdf
    with pikepdf.open(result.pdf) as pdf:
        page = pdf.pages[0]
        page.contents_coalesce()
        content = page.Contents.read_bytes().decode("latin1")  # pyright: ignore[reportAttributeAccessIssue]
    assert re.search(r"\b0 0 1 rg\b", content) and not re.search(r"\b1 0 0 rg\b", content)  # the renewed colour, blue
