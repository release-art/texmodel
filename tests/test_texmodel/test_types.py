"""Length and Colour (T4, T5): refusals, stable formatting, and the unit identities as properties."""

import math
from fractions import Fraction

import pytest
from hypothesis import (
    given,
    strategies as st,
)

from texmodel.errors import DeclarationError
from texmodel.types import CMYK, RGB, Gray, Length

NUMBERS = st.decimals(min_value=-10000, max_value=10000, places=4).map(str)
UNITS = st.sampled_from(["mm", "cm", "in", "pt", "bp", "pc", "em", "ex"])


def refused(code: str):
    return pytest.raises(DeclarationError, check=lambda e: e.code == code)


@given(NUMBERS, UNITS)
def test_a_length_survives_format_and_parse(number, unit):
    length = Length(f"{number}{unit}")
    assert Length(str(length)) == length and str(Length(str(length))) == str(length)
    assert Length(float(number), unit) == length  # float input agrees with str input


@given(st.integers(-1000, 1000), UNITS)
def test_trailing_zeros_do_not_change_the_output(n, unit):
    assert str(Length(f"{n}.000{unit}")) == str(Length(f"{n}{unit}")) == f"{n}{unit}"


@given(st.fractions(min_value=-1000, max_value=1000, max_denominator=100))
def test_the_absolute_units_agree_with_their_definitions(x):
    v = str(float(x))
    assert Length(v, "in").inches == Fraction(v)
    assert Length(v, "pt").inches * Fraction("72.27") == Fraction(v)  # pt = 1/72.27 in
    assert Length(v, "bp").inches * 72 == Fraction(v)  # bp = 1/72 in
    assert Length(v, "cm").inches * Fraction("2.54") == Fraction(v)
    assert Length(v, "mm").inches * Fraction("25.4") == Fraction(v)
    assert Length(v, "pc").inches * Fraction("72.27") == Fraction(v) * 12


def test_the_two_points_differ_and_a_big_point_is_bigger():
    assert Length("72.27pt").inches == Length("72bp").inches == 1
    assert Length("1bp").inches > Length("1pt").inches


@pytest.mark.parametrize(
    "bad", ["2", "mm", "", "2 mm", "2furlong", "1e3mm", "nanmm", "infpt", "--2mm", "2mmm", 2.0, float("nan")]
)
def test_malformed_lengths_are_refused(bad):
    with refused("TM-M016"):
        Length(bad)


def test_numbers_must_be_finite_and_well_formed_and_units_known():
    for args in ((math.inf, "mm"), (-math.inf, "mm"), (math.nan, "mm"), ("x", "mm"), (1, "furlong")):
        with refused("TM-M016"):
            Length(*args)


def test_relative_units_have_no_inches():
    with refused("TM-M016"):
        Length("1em").inches  # noqa: B018


def test_lengths_are_frozen_values():
    assert (
        Length("2mm") == Length("2.0mm")
        and hash(Length("2mm")) == hash(Length("2.0mm"))
        and Length("2mm") != Length("2cm")
    )
    assert (
        str(Length("-0.0mm")) == "0mm" and str(Length("+.50pt")) == "0.5pt" and str(Length(1e-05, "pt")) == "0.00001pt"
    )
    with pytest.raises(AttributeError):
        Length("2mm").unit = "cm"  # pyright: ignore[reportAttributeAccessIssue]


def test_colours_format_stably_and_keep_their_model():
    assert (CMYK.model, RGB.model, Gray.model) == ("cmyk", "rgb", "gray")
    assert str(CMYK(0, 0, 0, 0.95)) == "0,0,0,0.95" and str(CMYK(0.0, 1.0, 0.50, 1e-05)) == "0,1,0.5,0.00001"
    assert str(RGB(1, 0.5, 0)) == "1,0.5,0" and str(Gray(0.25)) == "0.25"
    assert CMYK(0, 0, 0, 1) != RGB(0, 0, 0)  # no conversion between models (T5)


@pytest.mark.parametrize("make", [lambda x: CMYK(0, 0, 0, x), lambda x: RGB(x, 0, 0), lambda x: Gray(x)])
@pytest.mark.parametrize("bad", [-0.01, 1.01, math.nan, math.inf])
def test_colour_components_outside_the_unit_interval_are_refused(make, bad):
    with refused("TM-M017"):
        make(bad)


def test_floats_are_rounded_to_five_decimals_and_strings_are_exact():
    from texmodel.types import Length, plain_number

    assert Length(0.1 + 0.2, "mm") == Length("0.3mm") and str(Length(78.8 / 100, "pt")) == "0.788pt"
    assert plain_number(0.7879999999999999) == "0.788" and plain_number(1 / 3) == "0.33333" and plain_number(2) == "2"
    assert str(Length("2.123456789mm")) == "2.123456789mm"
