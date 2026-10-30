"""`ext.table`: formats, columns from a row model, the parts of a table and the TeX they come to."""

import datetime
import decimal
import os
import re
from decimal import Decimal
from typing import Annotated

import pydantic
import pytest
from hypothesis import (
    given,
    settings,
    strategies as st,
)
from test_std.test_headers import compile_sample, host_compiler
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.components import Passthrough
from texmodel.document import Document
from texmodel.errors import DeclarationError, ValidationError
from texmodel.ext.table import (
    Col,
    Date,
    Flex,
    Format,
    Highlight,
    Label,
    Look,
    Money,
    Note,
    Number,
    Percent,
    Rules,
    Span,
    Table,
    Text,
    Total,
)
from texmodel.interface import ColourName
from texmodel.std import (
    latex,
    tabularray as t,
)
from texmodel.types import Length, Raw


class Sale(pydantic.BaseModel):
    region: Annotated[str, Col("Region", stub=True)]
    q1: Annotated[float, Col("Q1", group="2025", fmt=Number(0))]
    q2: Annotated[float | None, Col("Q2", group="2025", fmt=Number(0))]
    growth: Annotated[float, Col("Growth", fmt=Percent(1, sign=True), unit="%")]


ROWS = [
    Sale(region="N & S", q1=1200.5, q2=1340, growth=0.123),
    {"region": "East", "q1": -3, "q2": None, "growth": -0.05},
]


# --- formats -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fmt, value, tex",
    [
        (Number(0), 0, "0"),
        (Number(0), 999, "999"),
        (Number(0), 1000, r"1\,000"),
        (Number(2), 1234567.891, r"1\,234\,567.89"),
        (Number(0), 2.5, "3"),
        (Number(0), -2.5, "\u22123"),
        (Number(1), -0.04, "0.0"),
        (Number(1, sign=True), 3, "+3.0"),
        (Number(1, sign=True), 0, "0.0"),
        (Number(2, point="{,}", thousands=False), 1234.5, "1234{,}50"),
        (Number(0, separator="~"), 12345, "12~345"),
        (Number(0, minus="-"), -4, "-4"),
        (Number(0), Decimal("12.5"), "13"),
        (Number(1), None, "\u2013"),
        (Number(1, missing="n/a"), None, "n/a"),
        (Percent(1), 0.123, r"12.3\,\%"),
        (Percent(0, sign=True), 0.5, r"+50\,\%"),
        (Percent(0), -0.004, r"0\,\%"),
        (Text(), "a & b_c\n d", r"a \& b\_c d"),
        (Text(), Raw(r"\textbf{x}"), r"\textbf{x}"),
        (Text(), None, "\u2013"),
        (Money(symbol="€"), 1234.5, "€1\\,234.50"),
        (Money(symbol="€"), -5, "\u2212€5.00"),
        (Money(0, symbol="kr", after=True), 1500, "1\\,500\\,kr"),
        (Money(), 3, "3.00"),
        (Date(), datetime.date(2025, 3, 9), "2025-03-09"),
        (Date("%d %b %Y"), datetime.datetime(2025, 3, 9, 12), "09 Mar 2025"),
        (Label({True: "Yes", False: "No"}), False, "No"),
        (Label({"a": Raw(r"\emph{A}"), "b": "B & C"}), "a", r"\emph{A}"),
        (Label({"b": "B & C"}), "b", r"B \& C"),
    ],
)
def test_a_format_writes_a_value_as_escaped_tex(fmt, value, tex):
    assert fmt.tex(value) == tex


def test_a_format_is_one_that_says_how_it_writes():
    assert Format().tex(None) == "\u2013"
    with pytest.raises(NotImplementedError):
        Format().tex(1)


def test_a_date_and_a_label_refuse_what_they_do_not_know():
    with pytest.raises(TypeError):
        Date().tex("2025-03-09")
    with pytest.raises(ValueError):
        Label({"a": "A"}).tex("b")


@pytest.mark.parametrize("value", [True, "3", float("nan"), float("inf")])
def test_a_number_refuses_what_is_not_a_finite_number(value):
    with pytest.raises((TypeError, ValueError)):
        Number(0).tex(value)


def test_a_number_has_a_non_negative_number_of_decimals():
    with pytest.raises(DeclarationError) as raised:
        Number(-1)
    assert raised.value.code == "TM-M077"


@given(st.decimals(min_value=-(10**12), max_value=10**12, places=3), st.integers(0, 4))
def test_a_number_keeps_its_digits(value, decimals):
    text = Number(decimals, thousands=False, minus="-").tex(value)
    assert Decimal(text) == value.quantize(Decimal(1).scaleb(-decimals), rounding=decimal.ROUND_HALF_UP)


# --- columns -------------------------------------------------------------------------------------------------------


def test_a_column_defaults_by_type_and_a_float_asks_for_a_format():
    class Row(pydantic.BaseModel):
        name: str
        count: int
        free: Raw
        score: Annotated[float, Col(fmt=Number(1))]

    table = Table(Row, [Row(name="a", count=12345, free=Raw(r"\emph{x}"), score=1.25)])
    assert [c.label for c in table.columns] == ["Name", "Count", "Free", "Score"]
    assert [c.align for c in table.columns] == [t.HAlign.LEFT, t.HAlign.RIGHT, t.HAlign.LEFT, t.HAlign.RIGHT]
    assert r"a & 12\,345 & \emph{x} & 1.3 \\" in table.render()


@pytest.mark.parametrize("annotation", [float, bool, Decimal])
def test_a_type_with_no_default_format_needs_fmt(annotation):
    class Row(pydantic.BaseModel):
        value: annotation  # pyright: ignore[reportInvalidTypeForm]

    with pytest.raises(DeclarationError) as raised:
        Table(Row, [])
    assert (raised.value.code, raised.value.path) == ("TM-M078", "Row.value")


def test_a_number_format_needs_a_number_field():
    class Row(pydantic.BaseModel):
        name: Annotated[str, Col(fmt=Number(0))]

    with pytest.raises(DeclarationError) as raised:
        Table(Row, [])
    assert raised.value.code == "TM-M078"


@pytest.mark.parametrize("model", [dict, "Sale", None])
def test_a_table_needs_a_pydantic_model(model):
    with pytest.raises(DeclarationError) as raised:
        Table(model, [])  # pyright: ignore[reportArgumentType]
    assert raised.value.code == "TM-M077"


def test_a_table_needs_a_visible_column_and_one_stub_at_most():
    class Hidden(pydantic.BaseModel):
        a: Annotated[str, Col(hide=True)]

    class Stubs(pydantic.BaseModel):
        a: Annotated[str, Col(stub=True)]
        b: Annotated[str, Col(stub=True)]

    for model, code in ((Hidden, "TM-M077"), (Stubs, "TM-M079")):
        with pytest.raises(DeclarationError) as raised:
            Table(model, [])
        assert raised.value.code == code


def test_the_columns_of_a_group_are_next_to_each_other():
    class Split(pydantic.BaseModel):
        a: Annotated[str, Col(group="G")]
        b: str
        c: Annotated[str, Col(group="G")]

    with pytest.raises(DeclarationError) as raised:
        Table(Split, [])
    assert raised.value.code == "TM-M079"


def test_a_total_sums_visible_number_columns_only():
    for bad in ("region", "nope"):
        with pytest.raises(DeclarationError) as raised:
            Table(Sale, ROWS, totals=[Total("Total", sum=(bad,))])
        assert raised.value.code == "TM-M080"


def test_a_row_that_does_not_validate_names_its_index():
    with pytest.raises(ValidationError) as raised:
        Table(Sale, [ROWS[0], {"region": "x"}])
    assert (raised.value.code, raised.value.path) == ("TM-C026", "rows[1]")


def test_rows_may_come_from_a_generator():
    assert len(Table(Sale, (r for r in ROWS)).data) == 2


# --- the table -----------------------------------------------------------------------------------------------------


def test_a_table_is_a_caption_notes_header_groups_totals_and_rules():
    table = Table(Sale, ROWS, caption="Revenue", notes=[Note("Prov.")], totals=[Total("Total", sum=("q1", "q2"))])
    assert table.render() == "\n".join(
        [
            r"\begin{talltblr}[caption=Revenue,remark{Note}={Prov.}]{colspec=QQQQ,rowsep=0.5ex,colsep=6pt,"
            r"hline{1}={wd=0.08em},hline{2}={2-3}{wd=0.05em,lr,endpos},hline{3}={wd=0.05em},"
            r"row{1-2}={font=\bfseries},column{1}={leftsep=0pt},column{4}={rightsep=0pt},column{1}={halign=l},"
            r"column{2}={halign=r},column{3}={halign=r},column{4}={halign=r},cell{1}{2}={c=2}{halign=c},"
            r"row{5}={font=\bfseries},hline{5}={wd=0.05em},hline{Z}={wd=0.08em}}",
            r" & 2025 &  &  \\",
            r"Region & Q1 & Q2 & Growth (\%) \\",
            r"N \& S & 1\,201 & 1\,340 & +12.3\,\% \\",
            "East & \u22123 & \u2013 & \u22125.0\\,\\% \\\\",
            r"Total & 1\,198 & 1\,340 &  \\",
            r"\end{talltblr}",
        ]
    )


def test_a_plain_table_is_a_tblr_and_a_long_one_repeats_its_header():
    plain, long = Table(Sale, ROWS), Table(Sale, ROWS, long=True, label="tab:s", width=Length("10cm"))
    assert isinstance(plain.node(), t.Tblr) and plain.render().startswith(r"\begin{tblr}{colspec=QQQQ")
    assert isinstance(long.node(), t.Longtblr)
    assert "[label=tab:s]" in long.render() and "rowhead=2" in long.render() and "width=10cm" in long.render()


def test_a_column_may_be_flexible_or_fixed_and_take_a_column_spec():
    class Row(pydantic.BaseModel):
        a: Annotated[str, Col(width=Flex(2))]
        b: Annotated[
            str, Col(width=Length("3cm"), align=t.HAlign.CENTRE, style=t.ColumnSpec(bg=None, font=Raw(r"\small")))
        ]
        c: Annotated[str, Col(group=("Outer", "Inner"))]
        d: Annotated[str, Col(group=("Outer", "Inner"))]

    text = Table(Row, [Row(a="x", b="y", c="z", d="w")], width=Length("12cm"), rules=[t.row(3, t.RowSpec())]).render()
    assert "column{1}={halign=l,co=2}" in text and "column{2}={halign=c,wd=3cm}" in text
    assert r"column{2}={font=\small}" in text and text.endswith("\\end{tblr}") and "row{3}={}" in text
    assert "cell{1}{3}={c=2}{halign=c}" in text and "cell{2}{3}={c=2}{halign=c}" in text
    assert text.index("hline{2}={3-4}") < text.index("hline{3}={3-4}")


def test_a_look_sets_the_rules_and_the_header():
    look = Look(heavy=Length("1pt"), light=Length("0.5pt"), header_font=None)
    text = Table(Sale, ROWS, look=look).render()
    assert "hline{1}={wd=1pt}" in text and "hline{Z}={wd=1pt}" in text and "font=" not in text
    assert Look.BOOKTABS == Look()


@given(st.lists(st.text(min_size=1), min_size=1, max_size=4))
@settings(max_examples=60)
def test_whatever_the_cells_say_the_columns_stay_columns(cells):
    class Row(pydantic.BaseModel):
        a: str
        b: str

    rows = [Row(a=c, b=c) for c in cells]
    lines = Table(Row, rows).node().content[0].tex.tex.splitlines()  # pyright: ignore[reportAttributeAccessIssue]
    assert len(lines) == len(rows) + 1
    assert all(line.count(" & ") == 1 and line.endswith(r" \\") for line in lines)


# --- real TeX --------------------------------------------------------------------------------------------------------


class Wild(pydantic.BaseModel):
    text: str
    amount: Annotated[float, Col(fmt=Number(2))]


@pytest.mark.tex
@pytest.mark.timeout(900)
async def test_real_tex_sets_the_tables(compiler, tmp_path):  # noqa: F811
    """Every special character in every column, header groups, totals, notes, and a long table over several pages. In
    the reference image, or on this machine's TeX when the image lacks `tabularray` and TEXMODEL_STD_ON_HOST=1."""
    wild = [Wild(text=r"& % $ # _ { } ~ ^ \ x", amount=-1234.5), Wild(text="plain", amount=0.005)]
    long = [Wild(text=f"row {i}", amount=i * 1.5) for i in range(120)]
    tables = [
        Table(Sale, ROWS, caption="Revenue", notes=[Note("Prov.")], totals=[Total("Total", sum=("q1", "q2"))]),
        Table(Wild, wild),
        Table(Wild, long, long=True, caption="Long", label="tab:long"),
    ]
    plan = t.package.plan(Document(*(x.node() for x in tables), latex.Null()))
    result, errors, gaps = await compile_sample(compiler, plan, tmp_path)
    if gaps and len(gaps) == len(errors):
        host = host_compiler() if os.environ.get("TEXMODEL_STD_ON_HOST") else None
        if host is None:
            pytest.skip(f"the reference image lacks: {sorted({d.message for d in gaps})}")
        result, errors, gaps = await compile_sample(host, plan, tmp_path / "host")
    assert result.ok and not errors, [(d.path, d.code, d.message) for d in errors]
    assert Passthrough and re.search(r"\\begin\{longtblr\}", plan.text)


# --- phase 2: groups, highlights, spans, looks ----------------------------------------------------------------------


class Stock(pydantic.BaseModel):
    region: str
    city: Annotated[str, Col("City", stub=True)]
    amount: Annotated[float, Col("Amount", fmt=Money(symbol="€"))]
    ok: Annotated[bool, Col("OK", fmt=Label({True: "Yes", False: "No"}))]


STOCK = [
    Stock(region="North", city="A", amount=1000, ok=True),
    Stock(region="North", city="B", amount=-5.5, ok=False),
    Stock(region="South", city="C", amount=7, ok=True),
]


def test_rows_group_under_labels_with_subtotals_and_the_group_is_not_a_column():
    table = Table(Stock, STOCK, group_by="region", subtotal=Total("Subtotal", sum=("amount",)))
    text = table.render()
    assert [c.name for c in table.columns] == ["city", "amount", "ok"]
    assert (
        "\n".join(
            [
                "City & Amount & OK \\\\",
                "North &  &  \\\\",
                "A & €1\\,000.00 & Yes \\\\",
                "B & \u2212€5.50 & No \\\\",
                "Subtotal & €994.50 &  \\\\",
                "South &  &  \\\\",
                "C & €7.00 & Yes \\\\",
                "Subtotal & €7.00 &  \\\\",
            ]
        )
        in text
    )
    assert r"cell{2}{1}={c=3}{halign=l,font=\itshape}" in text and r"cell{6}{1}={c=3}{halign=l,font=\itshape}" in text
    assert "hborder{6}={abovespace=1ex}" in text and "hborder{2}" not in text
    assert r"cell{3-4}{1}={preto=\hspace{1em}}" in text and r"cell{7}{1}={preto=\hspace{1em}}" in text
    assert "row{5}={font=\\bfseries},hline{5}={wd=0.05em}" in text


def test_a_group_label_is_written_by_its_fields_format_and_a_hidden_field_can_group():
    class Hidden(pydantic.BaseModel):
        kind: Annotated[bool, Col(hide=True)]
        name: str

    text = Table(Hidden, [Hidden(kind=True, name="x")], group_by="kind").render()
    assert text.splitlines()[2] == r"True \\"
    ordered: list[Stock] = sorted(STOCK, key=lambda r: not r.ok)
    labelled = Table(Stock, ordered, group_by="ok")
    assert labelled.node().content[0].tex.tex.splitlines()[1].startswith("Yes")  # pyright: ignore[reportAttributeAccessIssue]


def test_the_rows_of_a_group_must_be_together_and_a_subtotal_needs_a_group():
    with pytest.raises(DeclarationError) as raised:
        Table(Stock, [STOCK[0], STOCK[2], STOCK[1]], group_by="region")
    assert raised.value.code == "TM-M081"
    for build in (
        lambda: Table(Stock, STOCK, group_by="nope"),
        lambda: Table(Stock, STOCK, subtotal=Total("S", sum=("amount",))),
    ):
        with pytest.raises(DeclarationError) as raised:
            build()
        assert raised.value.code == "TM-M081"
    with pytest.raises(DeclarationError) as raised:
        Table(Stock, STOCK, group_by="region", subtotal=Total("S", sum=("city",)))
    assert raised.value.code == "TM-M080"


def test_a_highlight_styles_the_rows_or_cells_where_its_predicate_holds():
    table = Table(
        Stock,
        STOCK,
        highlights=[
            Highlight(lambda r: r.amount < 0, columns=("amount", "ok"), fg=ColourName("red"), bold=True),
            Highlight(lambda r: r.city in ("A", "C"), bg=ColourName("yellow"), font=Raw(r"\small")),
            Highlight(lambda r: False, bold=True),
        ],
    )
    text = table.render()
    assert r"cell{3}{3-4}={fg=red,font=\bfseries}" in text
    assert r"row{2,4}={bg=yellow,font=\small}" in text and "font=\\bfseries}" in text
    assert text.count("row{") == 2  # the header's and the yellow ones: none for a predicate that never holds


def test_a_span_merges_cells_across_columns_where_its_predicate_holds():
    text = Table(
        Stock, STOCK, spans=[Span("amount", 2, where=lambda r: r.city == "C"), Span("city", 3, where=lambda r: False)]
    ).render()
    assert "cell{4}{3}={c=2}{}" in text and "South & C & €7.00 &  \\\\" in text
    assert text.count("cell{") == 1
    assert "cell{2-4}{2}={c=3}{}" in Table(Stock, STOCK, spans=[Span("city", 3)]).render()


def test_a_highlight_or_span_names_visible_columns_that_fit():
    for build in (
        lambda: Table(Stock, STOCK, group_by="region", highlights=[Highlight(lambda r: True, columns=("region",))]),
        lambda: Table(Stock, STOCK, group_by="region", spans=[Span("nope")]),
        lambda: Table(Stock, STOCK, group_by="region", spans=[Span("ok", 2)]),
        lambda: Table(Stock, STOCK, group_by="region", spans=[Span("city", 1)]),
    ):
        with pytest.raises(DeclarationError) as raised:
            build()
        assert raised.value.code == "TM-M082"


def test_a_look_may_be_a_grid_or_have_no_rules():
    grid, plain = Table(Stock, STOCK, look=Look.GRID).render(), Table(Stock, STOCK, look=Look.PLAIN).render()
    assert "hlines={wd=0.05em},vlines={wd=0.05em}" in grid and "hline{1}" not in grid and "leftsep" not in grid
    assert "hline" not in plain and "vline" not in plain and "leftsep" not in plain
    assert Look.GRID.rules is Rules.GRID and Look.PLAIN.rules is Rules.NONE
    assert "hline{" not in Table(Stock, STOCK, look=Look.PLAIN, totals=[Total("T", sum=("amount",))]).render()


@pytest.mark.tex
@pytest.mark.timeout(900)
async def test_real_tex_sets_groups_highlights_spans_and_grids(compiler, tmp_path):  # noqa: F811
    spans: list[Span[Stock]] = [Span("amount", 2, where=lambda r: r.city == "C")]
    marks: list[Highlight[Stock]] = [
        Highlight(lambda r: r.amount < 0, columns=("amount",), fg=ColourName("red"), bold=True)
    ]
    tables = [
        Table(
            Stock,
            STOCK,
            group_by="region",
            subtotal=Total("Subtotal", sum=("amount",)),
            totals=[Total("Total", sum=("amount",))],
            highlights=marks,
            spans=spans,
            caption="Stock",
        ),
        Table(Stock, STOCK, look=Look.GRID, highlights=marks),
        Table(
            Stock, STOCK, look=Look.PLAIN, long=True, highlights=[Highlight(lambda r: True, bg=ColourName("yellow"))]
        ),
    ]
    plan = t.package.plan(Document(*(x.node() for x in tables), latex.Null()))
    result, errors, gaps = await compile_sample(compiler, plan, tmp_path)
    if gaps and len(gaps) == len(errors):
        host = host_compiler() if os.environ.get("TEXMODEL_STD_ON_HOST") else None
        if host is None:
            pytest.skip(f"the reference image lacks: {sorted({d.message for d in gaps})}")
        result, errors, gaps = await compile_sample(host, plan, tmp_path / "host")
    assert result.ok and not errors, [(d.path, d.code, d.message) for d in errors]
