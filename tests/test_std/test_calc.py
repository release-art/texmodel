"""The `calc` header: a typed expression language. Rendering and typing are checked here; the values by compiling each
expression with the real package and comparing with arithmetic done in Python (text sizes: with `\\settowidth`)."""

import re

import pytest
from test_texmodel_build.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.std.calc import (
    AddToCounter,
    AddToLength,
    DimenExpr,
    GlueExpr,
    IntExpr,
    SetCounter,
    SetLength,
    SetToTotalHeight,
    count_register,
    counter_value,
    depthof,
    dimen,
    glue,
    heightof,
    integer,
    maxof,
    minof,
    package,
    ratio,
    real,
    totalheightof,
    widthof,
)
from texmodel.types import Length, LengthExpr, Raw
from texmodel_build.testkit import run_probes

PT = 72.27


def pt(text: str) -> float:
    return float(Length(text).inches) * PT


def cm(x: float) -> Length:
    return Length(x, "cm")


# --- rendering and typing ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "tex"),
    [
        (integer(7) / 2, "7/2"),
        (integer(3) * real(1.6), r"3*\real{1.6}"),
        (3 * integer(2) + 1, "3*2+1"),
        (1 + integer(2) * 3, "1+2*3"),
        ((integer(1) + 2) * 3, "(1+2)*3"),
        (integer(10) - (integer(2) - 3), "10-(2-3)"),
        (10 - integer(2), "10-2"),
        (integer(2) - integer(-3), "2-(-3)"),
        (integer(3) * (integer(1) + 2), "3*(1+2)"),
        (integer(3) * counter_value("c"), r"3*\value{c}"),
        (integer(3) * 2 / 4, "3*2/4"),
        (-integer(3), r"3*\real{-1}"),
        (+integer(3), "3"),
        (integer(3) * -2, "3*(-2)"),
        (
            integer(3) * maxof(integer(4) + 5, integer(3) * 4) + minof(integer(2) * real(1.6), integer(5) - 1),
            r"3*\maxof{4+5}{3*4}+\minof{2*\real{1.6}}{5-1}",
        ),
        (dimen(cm(2)) * real(1.5), r"2cm*\real{1.5}"),
        (dimen(cm(2)) * ratio(cm(3), cm(2)), r"2cm*\ratio{3cm}{2cm}"),
        (dimen(cm(6)) / 3, "6cm/3"),
        (3 * dimen(cm(1)), "1cm*3"),
        (dimen(cm(1)) + cm(2), "1cm+2cm"),
        (cm(2) + dimen(cm(1)), "2cm+1cm"),
        (cm(2) - dimen(cm(1)), "2cm-1cm"),
        (dimen(cm(1)) - (dimen(cm(2)) - cm(3)), "1cm-(2cm-3cm)"),
        ((dimen(cm(1)) + cm(2)) * 2, "(1cm+2cm)*2"),
        (-dimen(cm(2)), r"2cm*\real{-1}"),
        (dimen(Raw(r"\textwidth")) * real("0,5"), r"\textwidth*\real{0,5}"),
        (widthof("a & b") + heightof(Raw(r"\textbf{x}")), r"\widthof{a \& b}+\heightof{\textbf{x}}"),
        (depthof("x") - totalheightof("y"), r"\depthof{x}-\totalheightof{y}"),
        (maxof(dimen(cm(1)), cm(2)) + minof(cm(1), cm(2)), r"\maxof{1cm}{2cm}+\minof{1cm}{2cm}"),
        (glue(cm(1)), "1cm"),
        (glue(Length("3pt"), Length("1pt"), Length("2pt")), "3pt plus 1pt minus 2pt"),
        (glue(Length("1pt"), Raw("1fill")), "1pt plus 1fill"),
        (glue(Length("3pt"), Length("1pt")) + Length("2pt"), "3pt plus 1pt+2pt"),
        (glue(Length("3pt"), Length("1pt")) + dimen(Length("2pt")), "3pt plus 1pt+2pt"),
        (Length("2pt") + glue(Length("3pt")), "2pt+3pt"),
        (dimen(Length("2pt")) - glue(Length("3pt"), Length("1pt")), "2pt-(3pt plus 1pt)"),
        (Length("2pt") - glue(Length("3pt")), "2pt-3pt"),
        (glue(Length("3pt"), Length("3pt")) * real(1.5), r"(3pt plus 3pt)*\real{1.5}"),
        (glue(Length("3pt")) / 2, "3pt/2"),
        (-glue(Length("3pt")), r"3pt*\real{-1}"),
        (+glue(Length("3pt")) + glue(Length("1pt")), "3pt+1pt"),
        (maxof(glue(Length("3pt"), Length("1pt")), Length("2pt")), r"\maxof{3pt plus 1pt}{2pt}"),
        (minof(Length("2pt"), glue(Length("3pt"))), r"\minof{2pt}{3pt}"),
    ],
)
def test_an_expression_is_written_with_the_parentheses_it_needs(expression, tex):
    assert str(expression) == tex


def test_the_types_are_lengths_and_numbers_to_a_type_checker_and_to_a_field():
    assert isinstance(dimen(cm(1)), Length) and isinstance(glue(cm(1)), Length) and isinstance(integer(1), Raw)
    assert dimen(dimen(cm(1))) == dimen(cm(1)) and dimen(Raw(r"\parskip")).tex == r"\parskip"
    assert (
        SetLength(Raw(r"\parskip"), widthof("x") * real(0.5)).render()
        == r"\setlength{\parskip}{\widthof{x}*\real{0.5}}"
    )
    assert SetCounter(Raw("c"), integer(7) / 2).render() == r"\setcounter{c}{7/2}"
    assert AddToCounter(Raw("c"), integer(1)).render() == r"\addtocounter{c}{1}"
    assert AddToLength(Raw(r"\x"), glue(cm(1), cm(1))).render() == r"\addtolength{\x}{1cm plus 1cm}"
    assert SetToTotalHeight(Raw(r"\x"), Raw("Ag")).render() == r"\settototalheight{\x}{Ag}"
    (problem,) = SetCounter(Raw("c"), Raw("3")).validate()  # pyright: ignore[reportArgumentType]
    assert problem.code == "TM-C003" and "IntExpr" in problem.message


def test_an_expression_that_tex_would_refuse_is_refused_here():
    with pytest.raises(TypeError):
        integer(3) + dimen(cm(1))  # pyright: ignore[reportOperatorIssue, reportUnusedExpression]
    with pytest.raises(TypeError):
        integer(True)
    with pytest.raises(TypeError):
        dimen(cm(1)) * dimen(cm(2))  # pyright: ignore[reportArgumentType, reportOperatorIssue, reportUnusedExpression]
    with pytest.raises(TypeError):
        dimen(cm(1)) * True  # a bool is not a number  # pyright: ignore[reportUnusedExpression]
    with pytest.raises(TypeError):
        maxof(integer(1), cm(1))  # pyright: ignore[reportCallIssue, reportArgumentType]
    with pytest.raises(TypeError):
        maxof(1, 2)  # pyright: ignore[reportCallIssue, reportArgumentType]
    with pytest.raises(TypeError):
        dimen(glue(cm(1)))
    with pytest.raises(TypeError):
        integer(1) - 1.5  # pyright: ignore[reportOperatorIssue, reportUnusedExpression]
    for bad in ("x", "1.5.2", "", "1e3"):
        with pytest.raises(Exception, match="decimal constant"):
            real(bad)
    with pytest.raises(Exception, match="decimal constant"):
        real(True)  # pyright: ignore[reportArgumentType]


def test_a_real_number_may_have_signs_and_a_comma_and_is_written_plainly():
    assert real(2).tex == r"\real{2}" and real(0.50).tex == r"\real{0.5}" and real("- + 1,5").tex == r"\real{- + 1,5}"


def test_expressions_compare_by_text_and_not_by_how_tightly_they_bind():
    assert integer(1) + 2 == IntExpr("1+2") and dimen(cm(1)) == DimenExpr("1cm") and glue(cm(1)) == GlueExpr("1cm")
    assert isinstance(dimen(cm(1)), LengthExpr)


def test_commands_round_trip_through_data():
    node = SetLength(Raw(r"\x"), widthof("a") + cm(1))
    data = to_dict(node)
    assert data == {"type": "SetLength", "length": r"\x", "value": {"expr": r"\widthof{a}+1cm"}}
    assert from_dict(SetLength, data).render() == node.render()
    counter = SetCounter(Raw("c"), integer(2) * 3)
    assert to_dict(counter)["value"] == "2*3"
    loaded = from_dict(SetCounter, to_dict(counter))
    assert isinstance(loaded.value, IntExpr) and loaded.render() == counter.render()  # pyright: ignore[reportAttributeAccessIssue]
    assert json_schema(package)["$defs"]["SetCounter"]["properties"]["value"]["type"] == "string"


def test_the_header_declares_exactly_the_documented_commands():
    assert sorted(c.__name__ for c in package.registered) == [
        "AddToCounter",
        "AddToLength",
        "SetCounter",
        "SetLength",
        "SetToTotalHeight",
    ]


# --- the values, by compiling ------------------------------------------------------------------------------------

COUNT = [
    (integer(7) / 2, 3),
    (integer(3) * real(1.6), 4),
    (integer(3) * real(1.7), 5),
    (integer(3) * real(1.6) * real(1.7), 6),
    (integer(3) * maxof(integer(4) + 5, integer(3) * 4) + minof(integer(2) * real(1.6), integer(5) - 1), 39),
    (counter_value("c") * 2, 10),
    (-integer(3), -3),
    (integer(3) * (integer(1) + 2), 9),
    (integer(10) - (integer(2) - 3), 11),
    (3 * counter_value("c") - 1, 14),
    (integer(20) / counter_value("c") / 2, 2),
    (maxof(counter_value("c"), integer(2)) - minof(counter_value("c"), integer(2)), 3),
    (integer(2) * ratio(cm(3), cm(1)), 6),
    (count_register(Raw(r"\thec")) * 2 + count_register(Raw(r"\thec")), 15),  # a macro that expands to digits
]
DIMEN = [
    (dimen(cm(2)) * real(1.5), pt("3cm")),
    (dimen(cm(2)) * ratio(cm(3), cm(2)), pt("3cm")),
    (dimen(cm(6)) / 3, pt("2cm")),
    (dimen(cm(6)) / real(1.5), pt("4cm")),
    (dimen(cm(6)) / ratio(cm(3), cm(1)), pt("2cm")),
    (3 * dimen(cm(1)), pt("3cm")),
    (dimen(cm(1)) - (dimen(cm(2)) - cm(3)), pt("2cm")),
    (dimen(cm(1)) * (integer(1) + 2), pt("3cm")),
    (dimen(cm(1)) * counter_value("c"), pt("5cm")),
    ((dimen(cm(1)) + cm(2)) * 2, pt("6cm")),
    (-dimen(cm(2)), pt("-2cm")),
    (cm(2) + dimen(cm(1)), pt("3cm")),
    (cm(2) - dimen(cm(1)), pt("1cm")),
    (dimen(cm(1)) - Length("-5mm"), pt("1.5cm")),
    (maxof(dimen(cm(1)), cm(2)) + minof(cm(1), cm(2)), pt("3cm")),
    (dimen(Raw(r"\textwidth")) * real("0,5"), 172.5),
    (dimen(cm(2)) * ratio(widthof("abc") + cm(1), widthof("abc") + cm(1)), pt("2cm")),
]
GLUE = [
    (glue(Length("3pt"), Length("1pt"), Length("1pt")) + Length("2pt"), "5.0pt plus 1.0pt minus 1.0pt"),
    (glue(Length("3pt"), Length("3pt")) * real(1.5), "4.5pt"),
    (glue(Length("1pt"), Raw("1fill")), "1.0pt plus 1.0fill"),
    (Length("1pt") + glue(Length("2pt"), Length("1pt")), "3.0pt plus 1.0pt"),
    (glue(Length("6pt"), Length("2pt")) / 2, "3.0pt plus 1.0pt"),  # an integer keeps the stretch; a real drops it
    (maxof(glue(Length("3pt"), Length("1pt")), Length("2pt")), "3.0pt plus 1.0pt"),
    (minof(Length("2pt"), glue(Length("3pt"))), "2.0pt"),
]


def probe_document():
    lines = [r"\newcounter{c}\newlength{\tmd}\newlength{\tmg}\newlength{\tmo}\newlength{\tmp}"]
    body = []
    for i, (expression, _) in enumerate(COUNT):
        body.append(
            r"\setcounter{c}{5}"
            + SetCounter(Raw("c"), expression).render()
            + rf"\typeout{{texmodel:probe:i{i}=<\arabic{{c}}>}}"
        )
    for i, (expression, _) in enumerate(DIMEN):
        body.append(
            r"\setcounter{c}{5}"
            + SetLength(Raw(r"\tmd"), expression).render()
            + rf"\typeout{{texmodel:probe:d{i}=<\the\tmd>}}"
        )
    for i, (expression, _) in enumerate(GLUE):
        body.append(SetLength(Raw(r"\tmg"), expression).render() + rf"\typeout{{texmodel:probe:g{i}=<\the\tmg>}}")
    sizes = {"widthof": r"\settowidth", "heightof": r"\settoheight", "depthof": r"\settodepth"}
    for name, setter in sizes.items():
        function = {"widthof": widthof, "heightof": heightof, "depthof": depthof}[name]
        body.append(
            rf"{setter}{{\tmo}}{{Agjy}}"
            + SetLength(Raw(r"\tmd"), function("Agjy")).render()
            + rf"\typeout{{texmodel:probe:{name}=<\the\tmd|\the\tmo>}}"
        )
    body.append(
        SetToTotalHeight(Raw(r"\tmp"), Raw("Agjy")).render()
        + r"\settoheight{\tmo}{Agjy}\settodepth{\tmd}{Agjy}\addtolength{\tmo}{\tmd}"
        + SetLength(Raw(r"\tmd"), totalheightof("Agjy")).render()
        + r"\typeout{texmodel:probe:totalheightof=<\the\tmd|\the\tmo|\the\tmp>}"
    )
    body.append(
        SetLength(Raw(r"\tmd"), dimen(cm(1))).render()
        + AddToLength(Raw(r"\tmd"), dimen(cm(1)) * 2).render()
        + AddToCounter(Raw("c"), integer(3) * 2).render()
        + r"\typeout{texmodel:probe:adds=<\the\tmd|\arabic{c}>}"
    )
    return (
        "\\documentclass{article}\n\\usepackage{calc}\n\\begin{document}\n"
        + "\n".join(lines + body)
        + "\n\\null\n\\end{document}\n"
    )


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_every_expression_means_in_tex_what_the_arithmetic_says(compiler):  # noqa: F811
    found = {m.name: m.value for m in run_probes(compiler, probe_document())}

    def number(value: str) -> float:
        return float(re.fullmatch(r"<(-?[\d.]+)pt>", value)[1])  # pyright: ignore[reportOptionalSubscript]

    for i, (expression, expected) in enumerate(COUNT):
        assert found[f"i{i}"] == f"<{expected}>", str(expression)
    for i, (expression, expected) in enumerate(DIMEN):
        assert number(found[f"d{i}"]) == pytest.approx(expected, abs=0.01), str(expression)
    for i, (expression, expected) in enumerate(GLUE):
        assert found[f"g{i}"] == f"<{expected}>", str(expression)
    for name in ("widthof", "heightof", "depthof"):
        measured, oracle = found[name].strip("<>").split("|")
        assert measured == oracle and measured != "0.0pt", name
    total, oracle, direct = found["totalheightof"].strip("<>").split("|")
    assert total == oracle == direct
    assert number(found["adds"].split("|")[0] + ">") == pytest.approx(pt("3cm"), abs=0.01)
    assert found["adds"].endswith("|11>")


def test_the_header_package_loads_calc_once_when_a_body_uses_it():
    from texmodel.components import Command
    from texmodel.package import Package
    from texmodel.types import Text

    pkg = Package("calc-user", prefix="cu")

    @pkg.command
    class Indent(Command, unused=("text",)):
        """Indent by half the width of some text."""

        text: Text

        def body(self):
            yield SetLength.call(Raw(r"\parindent"), widthof("abc") * real(0.5))

    assert r"\RequirePackage{calc}" in pkg.render()


def test_the_remaining_operators_keep_to_the_same_rules():
    assert str(+dimen(cm(1))) == "1cm" and str(glue(cm(1), cm(1)) - cm(1)) == "1cm plus 1cm-1cm"
    assert str(3 * glue(cm(1))) == "1cm*3" and str(cm(1) - glue(cm(2), cm(1))) == "1cm-(2cm plus 1cm)"
    assert str(dimen(cm(1)) + glue(cm(2), cm(1))) == "1cm+(2cm plus 1cm)"
