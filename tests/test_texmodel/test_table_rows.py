"""Rows that are nodes: a `TableRow` command in a table, listed in `expand` so that tabularray expands it first."""

import pathlib
import re
import typing
from typing import Annotated

import pydantic
import pytest
from test_std.test_headers import compile_sample
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.components import Command, Passthrough
from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.ext import table as ext_table
from texmodel.ext.table import Col, Highlight, Look, Note, Span, Table, Total
from texmodel.package import Package
from texmodel.preamble import PreambleSlots
from texmodel.restore import Restored, restore
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.std import (
    latex,
    tabularray as t,
)
from texmodel.types import Length, Macro, Raw, Text

pkg = Package("acme-prof", prefix="ap")


@pkg.command
class ProfileRow(t.TableRow):
    """A profile row: one cell per field."""

    icon: Annotated[Raw, Col("", width=Length("6mm"))]
    label: Annotated[Text, Col("")]
    value: Annotated[Text, Col("", cells=t.CellSpec(font=Raw(r"\bfseries")))]


@pkg.command
class RatingRow(t.TableRow):
    """A rating row that spans its second cell."""

    label: Text
    stars: Text
    body = r"#label & \SetCell[c=2]{l} #stars & \\"


def rows() -> list[t.TableRow]:
    return [
        ProfileRow(icon=Raw("a"), label="Sound", value="Loud"),
        RatingRow(label="Taste", stars="four"),
        ProfileRow(icon=Raw("b"), label="Spot", value="Near"),
    ]


def table(*children: t.TableRow) -> t.Tblr:
    found = children or tuple(rows())
    return t.Tblr(*found, outer=t.TblrOuter(expand=t.expand_of(found)), inner=t.TblrInner(colspec=Raw("QQQ")))


def test_a_row_without_a_body_is_one_cell_per_field_in_order():
    assert ProfileRow(icon=Raw("a"), label="x", value="y").render() == r"\apProfileRow{a}{x}{y}"
    assert re.search(r"\\newcommand\{\\apProfileRow\}\[3\]\{%\n#1 & #2 & #3 \\\\\n\}", pkg.render())


def test_a_written_body_wins_and_the_base_is_never_registered():
    assert r"\SetCell[c=2]{l} #2 & \\" in pkg.render()
    assert t.TableRow not in pkg.registered and ProfileRow in pkg.registered


def test_a_row_command_takes_mandatory_arguments_in_braces_only():
    with pytest.raises(DeclarationError) as optional:

        class Loose(t.TableRow):
            """An optional cell."""

            a: Text
            b: Text | None = None

    assert optional.value.code == "TM-M084"


def test_a_subclass_of_a_row_that_adds_a_field_without_a_body_is_refused():
    with pytest.raises(DeclarationError) as raised:

        @Package("acme-wide", prefix="aw").command
        class Wider(ProfileRow):
            """One more cell, the inherited body does not write it."""

            extra: Text

    assert "never uses ['extra']" in str(raised.value)


def test_an_abstract_row_base_has_no_body_and_its_subclasses_derive_theirs():
    class Base(t.TableRow, abstract=True):
        a: Text

    class Narrow(Base):
        """A row of its own."""

    assert [a.name for a in Narrow.__tm_args__] == ["a"]


def test_expand_lists_each_row_command_once_in_order_of_first_use():
    assert t.expand_of(rows()) == Raw(r"\apProfileRow\apRatingRow")
    assert t.expand_of([Passthrough(Raw("a & b \\\\"))]) is None


def test_a_row_command_missing_from_expand_is_a_violation_that_names_the_row():
    bare = t.Tblr(*rows(), inner=t.TblrInner(colspec=Raw("QQQ")))
    assert [(v.code, v.path) for v in bare.violations()] == [
        ("TM-C027", "Tblr/ProfileRow[0]"),
        ("TM-C027", "Tblr/RatingRow[1]"),
        ("TM-C027", "Tblr/ProfileRow[2]"),
    ]
    assert table().violations() == []
    partly = t.Tblr(*rows(), outer=t.TblrOuter(expand=Raw(r"\apProfileRow")), inner=t.TblrInner(colspec=Raw("QQQ")))
    assert [v.path for v in partly.violations()] == ["Tblr/RatingRow[1]"]
    plus = t.Tblr(
        *rows(),
        outer=t.TblrOuter(expand=Raw(r"\apProfileRow"), expand_plus=Raw(r"\apRatingRow")),
        inner=t.TblrInner(colspec=Raw("QQQ")),
    )
    assert plus.violations() == []


def test_every_table_environment_checks_its_rows_and_a_plain_node_stays_refused():
    for env in (t.Longtblr, t.Talltblr, t.Booktabs, t.Longtabs, t.Talltabs):
        assert [v.code for v in env(*rows(), inner=t.TblrInner(colspec=Raw("QQQ"))).violations()] == ["TM-C027"] * 3

    @pkg.command
    class Stray(Command):
        """Not a row."""

        text: Text
        body = r"#text"

    stray = t.Tblr(Stray(text="x"), inner=t.TblrInner(colspec=Raw("Q")))
    assert [v.code for v in stray.violations()] == ["TM-C001"]


def test_a_row_floats_among_the_other_children_of_a_table():
    mixed = t.Tblr(
        Passthrough(Raw(r"Head & A & B \\")),
        *rows(),
        t.Hline(),
        outer=t.TblrOuter(expand=t.expand_of(rows())),
        inner=t.TblrInner(colspec=Raw("QQQ")),
    )
    assert mixed.violations() == []
    assert mixed.render().splitlines()[1:3] == [r"Head & A & B \\", r"  \apProfileRow{a}{Sound}{Loud}"]


def test_the_data_and_the_schema_know_the_row_classes():
    tree = table()
    data = to_dict(tree)
    assert [c["type"] for c in typing.cast("list[dict[str, str]]", data["content"])] == [
        "ProfileRow",
        "RatingRow",
        "ProfileRow",
    ]
    assert from_dict(t.Tblr, data) == tree
    defs = typing.cast("dict[str, object]", json_schema(t.Tblr)["$defs"])
    assert {"ProfileRow", "RatingRow"} <= set(defs) and "TableRow" not in defs
    assert {"ProfileRow", "RatingRow"} <= set(typing.cast("dict[str, object]", json_schema(pkg)["$defs"]))


def rows_of(done: Restored) -> list[str]:
    (tree,) = done.document.content
    assert isinstance(tree, t.Tblr)
    return [r.render() for r in tree.content if isinstance(r, t.TableRow)]


def test_a_hand_edit_of_one_cell_of_one_row_restores_to_that_field():
    document = Document(table())
    plan = pkg.plan(document)
    edits = plan.edits(plan.text.replace("{Sound}", "{Sonic}").replace("{four}", "{five}"))
    done = restore(pkg, document, edits)
    assert [u.reason for u in done.unapplied] == []
    assert rows_of(done) == [
        r"\apProfileRow{a}{Sonic}{Loud}",
        r"\apRatingRow{Taste}{five}",
        r"\apProfileRow{b}{Spot}{Near}",
    ]
    removed = restore(pkg, document, plan.edits(plan.text.replace("  \\apProfileRow{b}{Spot}{Near}\n", "")))
    assert rows_of(removed) == [r"\apProfileRow{a}{Sound}{Loud}", r"\apRatingRow{Taste}{four}"]


def test_a_table_from_a_row_class_writes_the_rows_as_nodes_and_lists_them():
    block = Table(ProfileRow, rows()[:1] + rows()[2:], header=False, look=Look.PLAIN)
    tree = block.node()
    assert tree.violations() == []
    shown = block.render()
    assert shown.splitlines()[0].startswith(r"\begin{tblr}[expand=\apProfileRow]")
    assert shown.splitlines()[1:3] == [r"  \apProfileRow{a}{Sound}{Loud}", r"  \apProfileRow{b}{Spot}{Near}"]
    assert "column{1}={halign=l,wd=6mm}" in shown and r"cell{1-2}{3}={font=\bfseries}" in shown


def test_the_header_is_one_passthrough_and_rows_count_after_it():
    labelled = Table(
        Labelled,
        [Labelled(a=Raw("a"), b="b")],
        look=Look.PLAIN,
        highlights=[Highlight(lambda r: True, bold=True)],
    )
    tree = labelled.node()
    assert isinstance(tree.content[0], Passthrough) and isinstance(tree.content[1], Labelled)
    assert re.search(r"row\{2\}=\{[^}]*font=\\bfseries", labelled.render())


@pkg.command
class Labelled(t.TableRow):
    """A row with labelled columns."""

    a: Annotated[Raw, Col("First")]
    b: Annotated[Text, Col("Second")]


def test_a_table_of_rows_refuses_what_the_row_command_writes():
    one = rows()[:1]
    for bad in (
        {"totals": [Total("T", sum=("label",))]},
        {"subtotal": Total("T", sum=("label",)), "group_by": "label"},
        {"group_by": "label"},
        {"spans": [Span("label", 2)]},
    ):
        with pytest.raises(DeclarationError) as raised:
            Table(ProfileRow, one, **bad)  # pyright: ignore[reportArgumentType]
        assert raised.value.code == "TM-M085"

    @pkg.command
    class Formatted(t.TableRow):
        """A column with a format of its own."""

        a: Annotated[Text, Col("A", fmt=ext_table.Text())]

    with pytest.raises(DeclarationError) as raised:
        Table(Formatted, [Formatted(a="x")])
    assert raised.value.code == "TM-M085"


def test_a_table_of_rows_keeps_the_caption_the_long_form_and_the_other_row_parts():
    caption = Table(Labelled, [Labelled(a=Raw("a"), b="b")], caption="Profile", notes=[Note("Note.")]).node()
    assert isinstance(caption, t.Talltblr) and caption.violations() == []
    assert r"expand=\apLabelled" in caption.render() and "caption=Profile" in caption.render()
    long = Table(Labelled, [Labelled(a=Raw("a"), b="b")], long=True).node()
    assert isinstance(long, t.Longtblr) and "rowhead=1" in long.render()
    empty = Table(Labelled, [], header=False).render()
    assert "expand" not in empty


def test_a_row_that_is_a_mapping_is_validated_by_its_class():
    made = Table(Labelled, [{"a": Raw("x"), "b": "y"}], header=False)
    assert [type(r) for r in made.data] == [Labelled]
    with pytest.raises(Exception) as raised:  # noqa: PT011
        Table(Labelled, [{"a": Raw("x")}], header=False)
    assert "row 0" in str(raised.value)


def test_a_plain_row_model_is_still_a_plain_table():
    class Plain(pydantic.BaseModel):
        a: Annotated[str, Col("A")]

    assert "expand" not in Table(Plain, [Plain(a="x")]).render()


SLOTS = PreambleSlots(after_package=(Raw(r"\usepackage{xcolor}\usepackage{tabularray}"),))


async def compile_rows(comp, node: t.Tblr | t.Talltblr | t.Longtblr, where: pathlib.Path):  # noqa: ANN001, ANN201
    """The node in a document that loads the package of its rows, written beside it."""
    (where / "src").mkdir(parents=True)
    (where / "src" / "acme-prof.sty").write_text(pkg.render(), encoding="utf-8")
    done = await compile_sample(comp, pkg.plan(Document(node, latex.Null(), preamble=SLOTS)), where)
    if done[2] and len(done[2]) == len(done[1]):
        pytest.skip(f"the reference image lacks: {sorted({d.message for d in done[2]})}")
    return done


@pytest.mark.tex
@pytest.mark.timeout(900)
async def test_real_tex_sets_rows_of_two_classes_in_one_table(compiler, tmp_path):  # noqa: F811
    result, errors, _ = await compile_rows(compiler, table(), tmp_path / "good")
    assert result.ok and not errors, [(d.path, d.code, d.message) for d in errors]


@pytest.mark.tex
@pytest.mark.timeout(900)
async def test_real_tex_sets_a_table_made_from_a_row_class(compiler, tmp_path):  # noqa: F811
    block = Table(Labelled, [Labelled(a=Raw("a"), b=f"row {i}") for i in range(130)], long=True)
    result, errors, _ = await compile_rows(compiler, block.node(), tmp_path)
    assert result.ok and not errors, [(d.path, d.code, d.message) for d in errors]


class ProfileColumns(t.TableRow, abstract=True):
    """The columns of a profile table; its row commands need not inherit them."""

    icon: Annotated[Raw, Col("", width=Length("6mm"))]
    label: Annotated[Text, Col("")]
    value: Annotated[Text, Col("", cells=t.CellSpec(font=Raw(r"\bfseries")))]


@pkg.command
class ProfileRowRating(t.TableRow):
    """A row with its own fields: the table takes only its columns from the layout."""

    icon: Raw
    label: Text
    score: int
    scale: int
    body = r"#icon & #label & \SetCell{l} #score / #scale \\"


def test_rows_of_any_node_class_share_the_columns_of_a_layout():
    mixed = Table(
        ProfileColumns,
        [
            ProfileRow(icon=Raw("a"), label="Sound", value="Loud"),
            ProfileRowRating(icon=Raw("b"), label="Taste", score=4, scale=5),
        ],
        header=False,
        look=Look.PLAIN,
    )
    assert r"expand=\apProfileRow\apProfileRowRating" in mixed.render()
    assert r"\apProfileRowRating{b}{Taste}{4}{5}" in mixed.render()


def test_a_row_with_fewer_cells_than_the_layout_has_columns_is_refused():
    @pkg.command
    class Short(t.TableRow):
        """Two cells."""

        icon: Raw
        label: Text

    with pytest.raises(DeclarationError, match="Short writes 2 cells, the layout ProfileColumns has 3") as raised:
        Table(ProfileColumns, [Short(icon=Raw("a"), label="x")], header=False)
    assert raised.value.code == "TM-M086"


envpkg = Package("acme-profenv", prefix="ae")
envpkg.require(t.package)


@envpkg.command
class EnvRow(t.TableRow):
    """A plain row."""

    icon: Raw
    label: Text
    value: Text


@envpkg.command
class EnvRating(t.TableRow):
    """A row without a value."""

    icon: Raw
    label: Text
    score: int
    body = r"#icon & #label & \SetCell{l} #score \\"


class EnvColumns(t.TableRow, abstract=True):
    """The columns."""

    icon: Annotated[Raw, Col("", width=Length("6mm"))]
    label: Annotated[Text, Col("")]
    value: Annotated[Text, Col("", cells=t.CellSpec(font=Raw(r"\bfseries")))]


@ext_table.declare(envpkg)
class Profile(ext_table.TableEnvironment):
    """A profile block."""

    columns = EnvColumns
    rows = (EnvRow, EnvRating)
    look = Look.PLAIN


def test_a_declared_table_environment_writes_its_layout_into_the_sty():
    sty = envpkg.render()
    assert r"\NewTblrEnviron{aeProfileTblr}" in sty
    assert r"\SetTblrOuter[aeProfileTblr]{expand=\aeEnvRow\aeEnvRating" in sty
    assert re.search(r"\\SetTblrInner\[aeProfileTblr\]\{colspec=QQQ", sty)
    doc = Profile(EnvRow(icon=Raw("a"), label="Size", value="L"), EnvRating(icon=Raw(""), label="Energy", score=4))
    assert doc.render().startswith(r"\begin{aeProfile}")


@pytest.mark.tex
@pytest.mark.timeout(900)
async def test_real_tex_sets_a_table_environment_the_package_owns(compiler, tmp_path):  # noqa: F811
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "acme-profenv.sty").write_text(envpkg.render(), encoding="utf-8")
    block = Profile(
        EnvRow(icon=Raw("a"), label="Size", value="L"),
        EnvRating(icon=Raw(""), label="Energy", score=4),
        outer=t.TblrOuter(caption="Profile"),
    )
    done = await compile_sample(compiler, envpkg.plan(Document(block, latex.Null(), preamble=SLOTS)), tmp_path)
    if done[2] and len(done[2]) == len(done[1]):
        pytest.skip(f"the reference image lacks: {sorted({d.message for d in done[2]})}")
    result, errors, _ = done
    assert result.ok and not errors, [(d.path, d.code, d.message) for d in errors]


collectpkg = Package("acme-collect", prefix="ac")
collectpkg.require(t.package)
collectpkg.library("Host", "\\newcounter{acItems}\\newcommand{\\hostStash}{}")


@collectpkg.command
class CollectItem(Command):
    """What the host does with a collected table: count it and keep the call."""

    item: Raw
    body = r"\stepcounter{acItems}\g@addto@macro\hostStash{#item}"


@collectpkg.command
class CollectRow(t.TableRow):
    """A row of a collected table."""

    icon: Raw
    label: Text
    value: Text


@ext_table.declare(collectpkg)
class Collected(ext_table.TableEnvironment):
    """A table the host collects and sets later."""

    columns = EnvColumns
    rows = (CollectRow,)
    look = Look.PLAIN
    collect = Macro(r"\acCollectItem")


def test_a_collecting_table_sets_a_box_and_hands_it_to_the_hosts_macro():
    sty = collectpkg.render()
    assert r"\newcounter{acCollectedBoxes}" in sty
    assert r"\global\expandafter\setbox\csname\@currenvir Box\arabic{\@currenvir Boxes}\endcsname\hbox\bgroup" in sty
    assert r"\unexpanded{\acCollectItem}{\noexpand\usebox" in sty
    assert r"\setbox" not in envpkg.render()  # a table without collect is set where it stands


def test_collect_takes_a_macro_with_arguments_and_is_inherited():
    class Host(Collected):
        """A further collecting table."""

        collect = Macro(r"\acCollectItem{front}")

    assert Host.collect == Macro(r"\acCollectItem{front}")
    assert Collected.collect == Macro(r"\acCollectItem")


@pytest.mark.tex
@pytest.mark.timeout(900)
async def test_real_tex_collects_the_table_and_sets_it_later(compiler, tmp_path):  # noqa: F811
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "acme-collect.sty").write_text(collectpkg.render(), encoding="utf-8")
    block = Collected(CollectRow(icon=Raw("a"), label="Size", value="L"), outer=t.TblrOuter(caption="Collected"))
    later = Passthrough(Raw(r"\par\hostStash\par items: \theacItems"))
    done = await compile_sample(
        compiler, collectpkg.plan(Document(block, later, latex.Null(), preamble=SLOTS)), tmp_path
    )
    if done[2] and len(done[2]) == len(done[1]):
        pytest.skip(f"the reference image lacks: {sorted({d.message for d in done[2]})}")
    result, errors, _ = done
    assert result.ok and not errors, [(d.path, d.code, d.message) for d in errors]


class SharedLook(ext_table.TableEnvironment, abstract=True):
    """A look the profile tables share."""

    look = Look.PLAIN
    columns = EnvColumns


def test_a_table_environment_inherits_what_it_does_not_set():
    @ext_table.declare(envpkg)
    class Inherited(SharedLook):
        """Rows of its own."""

        rows = (EnvRow,)

    assert Inherited.look is Look.PLAIN and Inherited.columns is EnvColumns
    assert Inherited(EnvRow(icon=Raw("a"), label="x", value="y")).violations() == []
    assert Inherited(EnvRating(icon=Raw("a"), label="x", score=1)).violations() != []  # not one of its rows
    assert r"\SetTblrOuter[aeInheritedTblr]{expand=\aeEnvRow}" in envpkg.render()


def test_a_table_environment_needs_columns_and_registered_rows():
    class NoColumns(ext_table.TableEnvironment):
        """No columns."""

        rows = (EnvRow,)

    with pytest.raises(DeclarationError, match="no columns") as raised:
        ext_table.declare(envpkg)(NoColumns)
    assert raised.value.code == "TM-M088"

    class Loose(t.TableRow):
        """Never registered."""

        icon: Raw
        label: Text
        value: Text

    class Unregistered(SharedLook):
        """Rows not registered."""

        rows = (Loose,)

    with pytest.raises(DeclarationError, match="Loose") as raised:
        ext_table.declare(envpkg)(Unregistered)
    assert raised.value.code == "TM-M087"

    class NoRows(SharedLook):
        """No rows."""

    with pytest.raises(DeclarationError, match="not registered") as raised:
        ext_table.declare(envpkg)(NoRows)
    assert raised.value.code == "TM-M087"
