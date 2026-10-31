"""A column as wide as the widest cell of the whole document, the tables of it included (`Widest`)."""

import pathlib
import re
from typing import Annotated

import pydantic
import pytest
from test_std.test_headers import compile_sample
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.document import Document
from texmodel.ext.table import Col, Look, Table, Widest
from texmodel.package import Package
from texmodel.preamble import PreambleSlots
from texmodel.std import (
    latex,
    tabularray as t,
)
from texmodel.types import Raw, Text

pkg = Package("acme-wide", prefix="aw")
label_width = Widest.declare(pkg, "LabelWidth")


class Line(pydantic.BaseModel):
    label: Annotated[str, Col("Label", width=label_width)]
    value: str


class Entry(t.TableRow):
    """A row of two cells, the first as wide as the widest label."""

    label: Annotated[Text, Col("", width=label_width)]
    value: Annotated[Text, Col("")]


pkg.command(Entry)


def test_a_widest_column_is_as_wide_as_the_recorded_length_and_its_cells_measure_themselves():
    shown = Table(Line, [Line(label="Sound", value="Loud")], look=Look.PLAIN).render()
    assert r"column{1}={halign=l,wd=\awLabelWidth}" in shown
    assert r"cell{1-2}{1}={cmd=\awMeasureLabelWidth}" in shown  # the label of the header and the body row
    assert r"\newcommand{\awMeasureLabelWidth}[1]{%" in pkg.render()
    assert r"\setbox\z@\hbox{#1}\awRecordLabelWidth{\the\wd\z@}#1" in pkg.render()
    assert r"\newlength{\awLabelWidth}" in pkg.render()


def test_without_a_header_only_the_body_cells_measure():
    shown = Table(Line, [Line(label="a", value="b")], header=False, look=Look.PLAIN).render()
    assert r"cell{1}{1}={cmd=\awMeasureLabelWidth}" in shown


def test_a_bad_name_is_refused():
    from texmodel.errors import DeclarationError

    with pytest.raises(DeclarationError) as raised:
        Widest.declare(pkg, "label")
    assert raised.value.code == "TM-M056"


def test_rows_that_are_nodes_measure_their_cells_too():
    shown = Table(Entry, [Entry(label="Sound", value="Loud")], header=False, look=Look.PLAIN).render()
    assert r"cell{1}{1}={cmd=\awMeasureLabelWidth}" in shown and r"\awEntry{Sound}{Loud}" in shown


@pytest.mark.tex
@pytest.mark.timeout(900)
async def test_real_tex_gives_two_tables_one_width(compiler, tmp_path: pathlib.Path):  # noqa: F811
    short = Table(Line, [Line(label="a", value="x")], look=Look.PLAIN)
    long = Table(Line, [Line(label="a much longer label", value="y")], look=Look.PLAIN)
    slots = PreambleSlots(after_package=(Raw(r"\usepackage{xcolor}\usepackage{tabularray}"),))
    plan = pkg.plan(Document(short.node(), long.node(), latex.Null(), preamble=slots))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "acme-wide.sty").write_text(pkg.render(), encoding="utf-8")
    result, errors, gaps = await compile_sample(compiler, plan, tmp_path)
    if gaps and len(gaps) == len(errors):
        pytest.skip(f"the reference image lacks: {sorted({d.message for d in gaps})}")
    assert result.ok and not errors, [(d.path, d.code, d.message) for d in errors]
    aux = next(tmp_path.rglob("d.aux")).read_text()
    (recorded,) = re.findall(r"\\aw@recLabelWidthread\{([\d.]+)pt\}", aux)
    assert float(recorded) > 40  # "a much longer label", not "a" (about 4pt)
    assert not any("not settled" in d.message for d in result.diagnostics)
