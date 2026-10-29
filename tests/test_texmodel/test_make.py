"""`Package.make_command` and `make_value`: classes from data, declared once per name."""

import pytest

from texmodel.components import field
from texmodel.errors import DeclarationError
from texmodel.package import Package, declared
from texmodel.types import CMYK, Colour, Length, Raw, Text


def region(pkg: Package, body: str = r"\bb@cardtitle{#name}", doc: str = "name: running"):
    return pkg.make_command("Name", doc, fields={"name": (Raw, field(doc="the name"))}, body=body, module="mods")


def test_a_made_command_is_registered_and_renders_like_a_written_one():
    pkg = Package("bb-demo", prefix="bb")
    label = pkg.make_command(
        "Label",
        "a labelled value",
        fields={"label": (Raw, field(doc="the label")), "text": (Raw | None, field(default=None))},
        body=r"\textbf{#label}#text",
    )
    assert label.__module__ == "bb-demo"
    assert [a.name for a in label.__tm_args__] == ["label", "text"]
    assert label.__tm_cs__ == "bbLabel"
    assert "\\newcommand{\\bbLabel}[2][]{%\n\\textbf{#2}#1\n}" in pkg.render()
    assert pkg.registered == (label,)


def test_the_same_data_again_is_the_class_made_first_and_other_data_is_refused():
    pkg = Package("bb-demo", prefix="bb")
    first = region(pkg)
    assert region(pkg) is first
    assert pkg.registered == (first,)
    assert region(Package("other", prefix="bb")) is not first
    for changed in ({"body": r"\bb@other{#name}"}, {"doc": "name: other"}):
        with pytest.raises(DeclarationError) as failed:
            region(pkg, **changed)
        assert failed.value.code == "TM-M007"
        assert "mods.Name" in str(failed.value)
    with pytest.raises(DeclarationError) as failed:
        pkg.make_command("Name", "name: running", fields={"name": (Raw | None, field(default=None))}, body=r"\x")
    assert failed.value.code == "TM-M007"


def test_a_made_value_has_its_kind_default_and_names():
    pkg = Package("bb-demo", prefix="bb")
    cut = pkg.make_value("TechCut", Colour, "the cut line", default=CMYK(0, 0.4, 1, 0), colour_name="bbTechCut")
    width = pkg.make_value("CardWidth", Length, "A6 short edge", default=Length("105mm"))
    label = pkg.make_value("FunFactsLabel", Text, "the header", default="Fun facts", cs="bbFunFacts")
    assert pkg.make_value("CardWidth", Length, "A6 short edge", default=Length("105mm")) is width
    assert (cut.colour_name, width.declared_default(), label.__tm_cs__) == ("bbTechCut", Length("105mm"), "bbFunFacts")
    text = pkg.render()
    assert r"\definecolor{bbTechCut}" in text
    assert r"\newlength{\bbCardWidth}" in text
    assert r"\newcommand{\bbFunFacts}{Fun facts}" in text
    with pytest.raises(DeclarationError) as failed:
        pkg.make_value("CardWidth", Length, "A6 short edge", default=Length("100mm"))
    assert failed.value.code == "TM-M007"


def test_a_made_component_a_library_defines_renders_no_definition():
    pkg = Package("bb-demo", prefix="bb")
    lib = pkg.library("own", r"\newcommand{\bbMark}[1]{#1}\newlength{\bbGap}")
    mark = pkg.make_command("Mark", "a mark", fields={"text": (Raw, field())}, defined_by=lib)
    gap = pkg.make_value("Gap", Length, "a gap", defined_by=lib)
    assert pkg.make_value("Gap", Length, "a gap", defined_by=lib) is gap
    assert (mark.defined_by, gap.defined_by) == (lib, lib)
    assert pkg.render().count(r"\newcommand{\bbMark}") == 1 and pkg.render().count(r"\newlength{\bbGap}") == 1
    assert r"\bbMark{x}" in pkg.document(mark(text=Raw("x")))
    with pytest.raises(DeclarationError) as failed:
        pkg.make_value("Gap", Length, "a gap")
    assert failed.value.code == "TM-M007"


def test_a_bare_default_is_a_field_default():
    pkg = Package("bb-demo", prefix="bb")
    made = pkg.make_command("Opt", "optional", fields={"x": (Raw | None, None)}, body=r"#x")
    assert pkg.make_command("Opt", "optional", fields={"x": (Raw | None, None)}, body=r"#x") is made
    assert made.__tm_args__[0].optional


def test_declared_is_the_names_the_scanner_reads_and_nothing_else():
    text = r"""
        \newcommand{\bbA}[1]{} \newlength{\bbB} \newif\ifbbC \definecolor{bbD}{rgb}{0,0,0} \newcounter{bbE}
        % \newcommand{\bbF}{}
        \def\bbG{} \let\bbH\relax \cs_new:Npn \bbI {} \write\f{\string\providecommand\string\bbJ}
    """
    assert declared(text) == {"bbA", "bbB", "ifbbC", "bbCtrue", "bbCfalse"}
