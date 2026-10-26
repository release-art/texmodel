"""`Value[Text]` (M1a): a text setting, `\\newcommand` with a default, `\\renewcommand` from a document."""

import pytest

from texmodel.components import Command, Value
from texmodel.document import Document
from texmodel.package import Package
from texmodel.types import Length, Text

from .test_document import refused


def generated():
    pkg = Package("txt-demo", prefix="tx")

    @pkg.value
    class Title(Value[Text]):
        """The deck title."""

        default = "R&D 50%"

    @pkg.value
    class Gap(Value[Length]):
        """A gap."""

        default = Length("2mm")

    @pkg.command
    class Show(Command):
        """Shows the title."""

        body = "\\txTitle #text"
        text: Text

    return pkg, Title, Gap, Show


def test_a_generated_package_defines_the_macro_with_an_escaped_default():
    pkg, *_ = generated()
    assert "% from test_texmodel.test_text_values.generated.<locals>.Title (value: Text)" in pkg.render()
    assert r"\newcommand{\txTitle}{R\&D 50\%}" in pkg.render()


def test_a_document_sets_every_value_right_after_the_package_in_the_order_given():
    from texmodel.preamble import PreambleSlots
    from texmodel.types import Raw

    pkg, title, gap, show = generated()
    plan = pkg.plan(
        Document(
            show(text="x"),
            settings=[gap(Length("3mm")), title("A & B")],
            preamble=PreambleSlots(after_package=(Raw(r"\x"),)),
        )
    )
    lines = [(x.path, x.tex) for x in plan.lines]
    order = [
        lines.index(("settings[0]", r"\setlength{\txGap}{3mm}")),
        lines.index(("settings[1]", r"\renewcommand{\txTitle}{A \& B}")),
        lines.index(("preamble.after_package[0]", r"\x")),
        lines.index(("document", r"\begin{document}")),
    ]
    assert order == sorted(order)


def test_the_value_is_checked_against_its_type():
    _, title, *_ = generated()
    with refused("TM-M014"):
        title(3)  # type: ignore[arg-type]


def test_a_text_value_needs_a_default_unless_the_package_is_adopted():
    pkg = Package("txt-demo", prefix="tx")

    class NoDefault(Value[Text]):
        """No default."""

    with refused("TM-M013"):
        pkg.value(NoDefault)

    adopted = Package("txt-demo", prefix="tx", adopted=True)
    adopted.value(NoDefault)
    assert adopted.files() == {}


def test_an_adopted_package_can_declare_only_a_text_value():
    adopted = Package("txt-demo", prefix="tx", adopted=True)

    class Gap(Value[Length]):
        """A gap."""

        default = Length("1mm")

    with refused("TM-P005"):
        adopted.value(Gap)


def test_an_adopted_text_value_is_checked_as_an_argument_less_command():
    adopted = Package("txt-demo", prefix="tx", adopted=True)

    @adopted.value
    class Title(Value[Text]):
        """The title."""

    assert adopted.check_interface(r"\newcommand{\txTitle}{x}") == []
    assert [v.code for v in adopted.check_interface("")] == ["TM-C010"]
    (bad,) = adopted.check_interface(r"\newcommand{\txTitle}[1]{x}")
    assert bad.code == "TM-C011" and "without arguments" in bad.message
    assert adopted.plan(Document(settings=[Title("Fox & Hen")])).text.count(r"\renewcommand{\txTitle}{Fox \& Hen}") == 1


def test_a_text_value_name_cannot_be_declared_twice():
    pkg, title, *_ = generated()
    with pytest.raises(Exception) as info:

        @pkg.value
        class Show(Value[Text]):
            """Clashes with the command."""

            default = "x"

    assert getattr(info.value, "code", "") == "TM-M007"


def test_setting_line_is_the_line_a_document_writes_for_a_setting():
    from texmodel.package import setting_line

    pkg, title, gap, _ = generated()
    assert setting_line(gap(Length("3mm"))) == r"\setlength{\txGap}{3mm}"
    assert setting_line(title("A & B")) == r"\renewcommand{\txTitle}{A \& B}"
