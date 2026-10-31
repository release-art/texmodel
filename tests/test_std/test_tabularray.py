"""tabularray's header: selectors, entries and the key lists they build (TeX accepting them is `test_headers`)."""

import pytest

from texmodel.components import Passthrough
from texmodel.errors import DeclarationError
from texmodel.interface import ColourName
from texmodel.std import tabularray as t
from texmodel.types import Length, Name, Raw


@pytest.mark.parametrize(
    "parts, tex",
    [
        ((1,), "1"),
        ((-1, "Z", "Y[2]"), "-1,Z,Y[2]"),
        (("2-4", "1-Z[2]", "Z[6]-Z[4]"), "2-4,1-Z[2],Z[6]-Z[4]"),
        (("odd", "even[3]", "-"), "odd,even[3],-"),
        (("every[2]{2}{-2}",), "every[2]{2}{-2}"),
    ],
)
def test_a_selector_is_indexes_ranges_and_child_selectors(parts, tex):
    assert t.selector(*parts).tex == tex


@pytest.mark.parametrize("parts", [(), ("1,Z",), ("even-odd",), ("A",), ("every{1}",), ("",)])
def test_a_selector_that_is_none_of_those_is_refused(parts):
    with pytest.raises(DeclarationError) as raised:
        t.selector(*parts)
    assert raised.value.code == "TM-M076"


def test_a_table_is_its_outer_and_inner_keys_around_its_rows_and_commands():
    node = t.Longtblr(
        Passthrough(Raw(r"a & b \\")),
        t.Hline(options=t.HlineSpec(dash=t.Dash.DASHED, l=True)),
        outer=t.TblrOuter(caption="A & B", rules=[t.note(Raw("a"), Raw("n")), t.remark(Raw("Source"), Raw("x"))]),
        inner=t.TblrInner(
            colspec=Raw("ll"),
            hlines=t.HlineSpec(),
            rules=[
                t.cell(1, 2, t.CellSpec(halign=t.HAlign.RIGHT, bg=ColourName("red"), math=True), span=t.CellSpan(c=2)),
                t.row("odd", t.RowSpec(abovesep_plus=Length("1pt"))),
                t.hline(t.selector(1, "Z"), t.HlineSpec(wd=Length("1pt")), "2-3"),
                t.hborder(2, t.HborderSpec(pagebreak=t.PageBreak.NO)),
            ],
        ),
    )
    assert node.render() == "\n".join(
        [
            r"\begin{longtblr}[caption=A \& B,note{a}={n},remark{Source}={x}]{colspec=ll,hlines={},"
            r"cell{1}{2}={c=2}{halign=r,bg=red,$},row{odd}={abovesep+=1pt},hline{1,Z}={2-3}{wd=1pt},"
            r"hborder{2}={pagebreak=no}}",
            r"a & b \\",
            r"  \hline[dash=dashed,l]",
            r"\end{longtblr}",
        ]
    )


def test_the_other_entries_name_their_selector():
    assert [
        e.tex
        for e in (
            t.cells(t.CellSpec(halign=t.HAlign.LEFT), span=t.CellSpan(r=2)),
            t.cell(t.Selector("mine"), "-", t.CellSpec()),
            t.column(2, t.ColumnSpec(co=1)),
            t.vline("Y[2]", t.VlineSpec(), "odd"),
            t.hlines(t.HlineSpec(), 1),
            t.vlines(t.VlineSpec(dash=t.Dash.DOTTED)),
            t.vborder(2, t.VborderSpec(leftspace_plus=Length("1pt"))),
        )
    ] == [
        "cells={r=2}{halign=l}",
        "cell{mine}{-}={}",
        "column{2}={co=1}",
        "vline{Y[2]}={odd}{}",
        "hlines={1}{}",
        "vlines={dash=dotted}",
        "vborder{2}={leftspace+=1pt}",
    ]


def test_the_commands_inside_a_table_write_their_optional_argument_first():
    assert (
        t.SetCell(span=t.CellSpan(r=2), spec=t.CellSpec(halign=t.HAlign.CENTRE)).render() == r"\SetCell[r=2]{halign=c}"
    )
    assert t.SetHline(columns=t.selector("2-3"), spec=t.HlineSpec()).render() == r"\SetHline{2-3}{}"
    assert t.Cline(columns=t.selector(2), options=t.HlineSpec(dash=t.Dash.DASHED)).render() == r"\cline[dash=dashed]{2}"
    assert (
        t.NewTblrColumnType(name=Name("t"), count=1, definition=Raw("Q[t]")).render()
        == r"\NewTblrColumnType{t}[1]{Q[t]}"
    )
    assert (
        t.NewTblrColumnType(name=Name("t"), count=1, default=Raw("2cm"), definition=Raw("Q[t]")).render()
        == r"\NewTblrColumnType{t}[1][2cm]{Q[t]}"
    )
