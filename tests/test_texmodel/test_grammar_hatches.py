"""`Anywhere` and `Passthrough` (B3): a term that floats, and TeX written as it is."""

from hypothesis import (
    given,
    strategies as st,
)

from texmodel.components import Anywhere, Command, Environment, Passthrough
from texmodel.package import Package
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import Raw, Text

from .test_document import refused

pkg = Package("hatch", prefix="ht")


@pkg.command
class Head(Command):
    """A heading."""

    body = "#text"
    text: Text


@pkg.command
class Item(Command):
    """An item."""

    body = "#text"
    text: Text


@pkg.environment
class Page(Environment):
    """A page: one head, two or three items, headings anywhere."""

    children = [Head, Item.times(2, 3), Anywhere(Passthrough)]
    begin = r"\begin{center}"
    end = r"\end{center}"


@pkg.environment
class Sheet(Environment):
    """Items with headings anywhere."""

    children = [Item.times(2, 3), Anywhere(Head), Passthrough.times.any()]
    begin = r"\begin{flushleft}"
    end = r"\end{flushleft}"


V = Passthrough(Raw(r"\vspace{1mm}"))


def test_a_passthrough_renders_its_tex_and_is_a_node_anywhere_it_is_listed():
    assert (
        V.render() == r"\vspace{1mm}" and V.violations() == [] and repr(V) == "Passthrough(Raw(tex='\\\\vspace{1mm}'))"
    )
    assert Page(V, Head(text="h"), V, Item(text="a"), V, Item(text="b"), V).violations() == []
    assert pkg.document(Page(Head(text="h"), V, Item(text="a"), Item(text="b"))).count(r"\vspace{1mm}") == 1


def test_a_passthrough_where_no_grammar_lists_it_is_refused():
    assert Sheet(Item(text="a"), Item(text="b"), V).violations() == []  # Sheet lists Passthrough.times.any()
    (bad,) = Page(Head(text="h"), Item(text="a"), Item(text="b"), Item(text="c"), Item(text="d")).violations()
    assert bad.code == "TM-C001" and bad.path == "Page/Item[4]"
    assert [v.code for v in Sheet(Item(text="a"), Head(text="h")).violations()] == ["TM-C002"]  # one Item is too few


@given(st.lists(st.booleans(), min_size=3, max_size=3), st.integers(2, 3), st.integers(0, 3))
def test_any_interleaving_of_anywhere_items_keeps_the_ordered_run_valid(heads_before, n, trailing):
    """A heading before each item, after the last, or none: never changes whether the items are valid."""
    mixed: list = []
    for i in range(n):
        mixed += ([Head(text=f"h{i}")] if heads_before[i % 3] else []) + [Item(text=str(i))]
    mixed += [Head(text="end")] * trailing
    assert Sheet(*mixed).violations() == []


def test_counts_are_still_enforced_and_paths_keep_the_real_position():
    (few,) = Sheet(Head(text="a"), Item(text="a"), Head(text="b")).violations()
    assert few.code == "TM-C002" and "found 1" in few.message
    many = Sheet(Item(text="a"), Head(text="h"), Item(text="b"), Item(text="c"), Item(text="d")).violations()
    assert [(v.code, v.path) for v in many] == [("TM-C001", "Sheet/Item[4]")]


def test_a_kind_cannot_be_ordered_and_anywhere_nor_anywhere_a_non_component():
    with refused("TM-M029"):

        class Both(Environment):
            """x"""

            children = [Item, Anywhere(Item)]
            begin = end = "x"

    with refused("TM-M020"):

        class Odd(Environment):
            """x"""

            children = [Anywhere(int)]
            begin = end = "x"


def test_data_round_trip_and_schema_know_both():
    node = Sheet(Item(text="a"), Head(text="h"), V, Item(text="b"))
    data = to_dict(node)
    assert data["content"][2] == {"type": "Passthrough", "tex": r"\vspace{1mm}"}  # type: ignore[index]
    assert from_dict(Sheet, data) == node
    assert set(json_schema(Sheet)["$defs"]) >= {"Head", "Item", "Passthrough"}
    assert str(Anywhere(Head)) == "Head anywhere"


@pkg.environment
class Slide(Environment):
    """Anything: TeX as it is and the commands and environments of any package."""

    children = [Anywhere(Passthrough), Anywhere(Command), Anywhere(Environment)]
    begin = r"\begin{center}"
    end = r"\end{center}"


def test_anywhere_a_command_or_environment_takes_any_component_and_nothing_else():
    other = Package("elsewhere", prefix="el")

    @other.command
    class Foreign(Command):
        """Declared by another package."""

        body = "#text"
        text: Text

    slide = Slide(V, Head(text="h"), Foreign(text="f"), Page(Head(text="p"), Item(text="a"), Item(text="b")))
    assert slide.violations() == []
    assert pkg.document(slide).count(r"\elForeign{f}") == 1
    assert str(Anywhere(Command)) == "Command anywhere"
    bad = Slide(Page(Head(text="h")))  # the child's own grammar still applies
    assert [v.code for v in bad.violations()] == ["TM-C002"]


def test_data_lists_no_component_for_a_wildcard_term_and_the_schema_still_builds():
    assert set(json_schema(Slide)["$defs"]) >= {"Passthrough"}
    assert from_dict(Slide, to_dict(Slide(V))) == Slide(V)
