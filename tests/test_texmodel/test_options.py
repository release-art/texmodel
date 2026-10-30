"""Package options (§21): l3keys keys read once when the package loads, declared by whichever module needs them, set by
a document in `\\usepackage[...]`."""

import enum

import pytest
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.components import Value
from texmodel.document import Document
from texmodel.errors import DeclarationError
from texmodel.package import Package, declared, setting_line
from texmodel.preamble import PreambleSlots
from texmodel.run.testkit import run_probes
from texmodel.spec import from_dict, to_dict
from texmodel.types import Choice, Length, Raw, Text


@enum.unique
class Accent(Choice):
    """A deck's accent."""

    SLATE = Raw("slate grey")
    MOSS = "moss & fern"
    DEEP_SEA = Raw("deep")


def deck() -> tuple[Package, type[Value[bool]], type[Value[Length]], type[Value[Accent]]]:
    pkg = Package("acme-options", prefix="ao")
    crop = pkg.option("crop", flag=True, inverse="nocrop", doc="The print build.", cs="aoshowcrop")
    bleed = pkg.option("bleed", length=Length("3mm"), doc="The bleed.")
    accent = pkg.option("accent", choice=Accent.SLATE, doc="The accent.")

    @pkg.value
    class Title(Value[Text]):
        """Not an option."""

        default = "Cards"

    return pkg, crop, bleed, accent  # pyright: ignore[reportReturnType]


def test_the_options_section_comes_after_the_packages_and_before_everything_else():
    pkg, *_ = deck()
    sty = pkg.render()
    lines = sty.splitlines()
    assert lines.index(r"\ExplSyntaxOn") < lines.index(r"\ProcessKeyOptions [ acme-options ]") < sty.count("\n")
    assert sty.index("ProcessKeyOptions") < sty.index(r"\newcommand{\aoTitle}")
    for key in (
        "crop .legacy_if_set:n = aoshowcrop ,",
        "nocrop .legacy_if_set_inverse:n = aoshowcrop ,",
        "bleed .code:n = \\setlength { \\aoBleed } {#1} ,",
        "bleed .value_required:n = true ,",
        "accent .choice: ,",
        "accent / deep-sea .code:n = \\cs_set_eq:Nc \\aoAccent { aoAccent@deep-sea } ,",
    ):
        assert f"    {key}" in lines
    assert all(f"{n} .usage:n = load ," in sty for n in ("crop", "nocrop", "bleed", "accent"))
    assert r"\@namedef{aoAccent@moss}{moss \& fern}" in sty and r"\newcommand{\aoAccent}{slate grey}" in sty
    assert {"ifaoshowcrop", "aoBleed", "aoAccent"} <= declared(sty)  # the scanner reads the registers
    assert pkg.check_parts() == [] and [p.path for p in pkg.render_plan().lines if p.tex == r"\ExplSyntaxOff"] == [
        "options"
    ]


def test_a_document_sets_an_option_in_usepackage_and_other_values_after_it():
    pkg, crop, bleed, accent = deck()
    title = next(c for c in pkg.registered if c.__name__ == "Title")
    tex = pkg.document(Document(settings=[crop(False), title("Owls"), bleed(Length("2mm")), accent(Accent.DEEP_SEA)]))
    assert r"\usepackage[crop=false,bleed=2mm,accent=deep-sea]{acme-options}" in tex
    assert tex.index(r"\usepackage[") < tex.index(r"\renewcommand{\aoTitle}{Owls}")
    assert r"\usepackage{acme-options}" in pkg.document(Document())
    with pytest.raises(DeclarationError) as raised:
        setting_line(accent(Accent.MOSS))  # a choice has no setting after the package: it is an option
    assert raised.value.code == "TM-M072"
    data = to_dict(Document(settings=[accent(Accent.MOSS)]))
    assert data["settings"] == [{"type": "Accent", "value": "MOSS"}] and to_dict(from_dict(pkg, data)) == data


def test_an_option_of_a_base_is_passed_to_it_before_the_package_loads():
    base, crop, _, _ = deck()
    derived = Package("acme-derived", prefix="ad", base=base)
    tex = derived.document(Document(settings=[crop(True)]))
    assert r"\PassOptionsToPackage{crop=true}{acme-options}" in tex
    assert tex.index("PassOptionsToPackage") < tex.index(r"\usepackage{acme-derived}")


def test_a_module_that_declares_an_option_again_the_same_way_shares_it():
    pkg, crop, *_ = deck()
    assert pkg.option("crop", flag=True, inverse="nocrop", doc="Said again.", cs="aoshowcrop") is crop
    assert pkg.options.count(crop) == 1 and len(pkg.options) == 3


@pytest.mark.parametrize(
    "again",
    [
        {"flag": False, "inverse": "nocrop", "cs": "aoshowcrop"},  # another default
        {"length": Length("1mm")},  # another kind
        {"flag": True, "inverse": "plain", "cs": "aoshowcrop"},  # another inverse
        {"flag": True, "inverse": "nocrop"},  # another control sequence
    ],
)
def test_an_option_declared_again_differently_is_refused(again):
    pkg, *_ = deck()
    with pytest.raises(DeclarationError) as raised:
        pkg.option("crop", doc="Again.", **again)
    assert raised.value.code == "TM-M073"


def test_a_key_already_taken_by_another_option_is_refused():
    pkg, *_ = deck()
    for name, inverse in (("nocrop", None), ("trim", "crop"), ("trim", "nocrop")):
        with pytest.raises(DeclarationError) as raised:
            pkg.option(name, flag=False, inverse=inverse, doc="Clashes.")
        assert raised.value.code == "TM-M073"


@pytest.mark.parametrize(
    ("package", "name", "given"),
    [
        (Package("acme-x", prefix="ax"), "Crop", {"flag": True}),  # not a lowercase key
        (Package("acme-x", prefix="ax"), "a4", {"flag": True}),  # a digit names no macro
        (Package("acme-x", prefix="ax"), "crop", {}),  # no kind
        (Package("acme-x", prefix="ax"), "crop", {"flag": True, "length": Length("1mm")}),  # two kinds
        (Package("acme-x", prefix="ax"), "bleed", {"length": Length("1mm"), "inverse": "nobleed"}),
        (Package("acme-x", prefix="ax"), "crop", {"flag": True, "inverse": "crop"}),
        (Package("acme-x", prefix="ax"), "crop", {"flag": True, "inverse": "No"}),
        (Package("acme-bare", prefix=""), "crop", {"flag": True}),  # no prefix and no cs
        (Package("latex", prefix="", builtin=True), "crop", {"flag": True, "cs": "crop"}),  # no \usepackage
    ],
)
def test_an_option_that_cannot_work_is_refused(package, name, given):
    with pytest.raises(DeclarationError) as raised:
        package.option(name, doc="Bad.", **given)
    assert raised.value.code == "TM-M072"


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_the_keys_set_the_registers_when_the_package_loads(compiler):  # noqa: F811
    """Measured: the defaults hold, a document's settings arrive through `\\usepackage[...]`, a class option reaches
    the package, and a choice member's TeX keeps its spaces."""
    pkg, crop, bleed, accent = deck()
    probe = Raw(
        r"\typeout{texmodel:probe:crop=\ifaoshowcrop true\else false\fi}"
        r"\typeout{texmodel:probe:bleed=\the\aoBleed}\typeout{texmodel:probe:accent=\aoAccent}"
    )

    async def run(document: Document) -> dict[str, str]:
        tex = pkg.document(document).replace(r"\begin{document}", r"\begin{document}x")
        return {m.name: m.value for m in await run_probes(compiler, tex, {f"{pkg.name}.sty": pkg.render()})}

    after = PreambleSlots(after_package=(probe,))
    assert await run(Document(preamble=after)) == {"crop": "true", "bleed": "8.53581pt", "accent": "slate grey"}
    chosen = [crop(False), bleed(Length("2mm")), accent(Accent.MOSS)]
    assert await run(Document(settings=chosen, preamble=after)) == {
        "crop": "false",
        "bleed": "5.69054pt",
        "accent": r"moss \& fern",
    }
    assert (await run(Document(options=["nocrop"], preamble=after)))["crop"] == "false"
