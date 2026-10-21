import importlib.metadata
import pathlib

import pytest

from texmodel import drift
from texmodel.components import Command, snake
from texmodel.errors import DeclarationError
from texmodel.package import Package, generator_version
from texmodel.types import TEXT, Text

GOLDEN = pathlib.Path(__file__).parent.parent / "fixtures" / "acme_cards" / "generated"


def pkg(**kw) -> Package:
    return Package("p", prefix="t", **kw)


def refused(code: str):
    return pytest.raises(DeclarationError, check=lambda e: e.code == code)


def test_the_fixture_package_renders_exactly_the_committed_golden(acme):
    # Regenerate with: pdm run python -c "..." (see CONTRIBUTING); a diff here is an output change (G7).
    result = drift.check_drift(acme.pkg.files(version="0.1.0"), GOLDEN, owned=("*.sty",))
    assert result.ok, f"generated output differs from {GOLDEN}: {result}"


def test_rendering_is_deterministic_and_stamped(acme):
    assert acme.pkg.render(version="0.1.0") == acme.pkg.render(version="0.1.0")
    first_line = acme.pkg.render(version="0.1.0").splitlines()[0]
    assert "generated with texmodel 0.1.0" in first_line and first_line.startswith("% acme-cards.sty")


def test_arguments_follow_tex_order_with_the_optional_one_first(acme):
    text = acme.pkg.render(version="0.1.0")
    assert "\\newcommand{\\acSlot}[2][]{%" in text and "#1\\relax\\else{\\bfseries #1\\quad}" in text
    assert "\\newcommand{\\acRule}{%" in text  # no arguments: no signature
    assert "\\newcommand{\\acName}[1]{%" in text


def test_optional_fields_are_keyword_only_and_components_are_frozen(acme):
    assert acme.Slot("a", label="b").label == "b" and acme.Slot("a").label is None
    with pytest.raises(TypeError):
        acme.Slot("a", "b")  # pyright: ignore[reportCallIssue]
    with pytest.raises(AttributeError):
        acme.Slot("a").text = "x"  # pyright: ignore[reportAttributeAccessIssue]
    assert acme.Fact("x") == acme.Fact("x") and hash(acme.Fact("x")) == hash(acme.Fact("x"))


def test_package_arguments_are_validated():
    for kw, code in (
        ({"name": "Bad Name", "prefix": "t"}, "TM-P001"),
        ({"name": "p", "prefix": "T1"}, "TM-P002"),
        ({"name": "p", "prefix": "t", "date": "2026-10-21"}, "TM-P003"),
    ):
        with refused(code):
            Package(**kw)


def test_declarations_are_refused_when_the_class_is_defined():
    with refused("TM-M001"):

        class Fact2(Command):
            """Digits cannot be in a control word."""

    with refused("TM-M001"):

        class lower(Command):  # noqa: N801
            """Starts with a capital."""

    with refused("TM-M002"):

        class Undocumented(Command):
            text: Text

    with refused("TM-M003"):

        class TwoOptional(Command):
            """Two optional arguments."""

            a: Text | None = None
            b: Text | None = None

    with refused("TM-M004"):

        class WrongType(Command):
            """An int field."""

            n: int


def test_a_missing_or_ambiguous_body_is_an_error_naming_the_file():
    p = pkg()
    with refused("TM-M006") as info:

        @p.command
        class NoBody(Command):
            """No body anywhere."""

    assert "no_body.tex" in str(info.value)


def test_a_class_with_both_an_inline_body_and_a_body_file_is_ambiguous(tmp_path, monkeypatch):
    (tmp_path / "ambig_mod.py").write_text(
        'from texmodel.components import Command\nclass Thing(Command, body=\'x\'):\n    """Doc."""\n'
    )
    (tmp_path / "thing.tex").write_text("y")
    monkeypatch.syspath_prepend(str(tmp_path))
    import ambig_mod  # pyright: ignore[reportMissingImports]

    with refused("TM-M005"):
        pkg().command(ambig_mod.Thing)


def test_body_lints():
    p = pkg()
    with refused("TM-M009"):

        @p.command
        class Unknown(Command, body="#nope"):
            """Hole is not a field."""

            text: Text

    with refused("TM-M008"):

        @p.command
        class Digit(Command, body="#1"):
            """Numbered hole."""

            text: Text

    with refused("TM-M010"):

        @p.command
        class Forgot(Command, body="x"):
            """Never uses its argument."""

            text: Text

    with refused("TM-M011"):

        @p.command
        class Stray(Command, body="}#text"):
            """Closes what was never opened."""

            text: Text

    with refused("TM-M011"):

        @p.command
        class Open(Command, body="{#text"):
            """Unbalanced."""

            text: Text

    @p.command
    class Ok(Command, body="\\{ #text \\} % { comment", unused=()):
        """Escaped braces and a comment brace are fine."""

        text: Text

    @p.command
    class Skips(Command, body="x", unused=("text",)):
        """Declares the argument unused."""

        text: Text

    @p.command
    class Hash(Command, body="##\\par #text"):
        """A literal # is written ##."""

        text: Text

    assert "##\\par #1" in p.render(version="0")


def test_a_name_collision_is_an_error_at_registration():
    p = pkg()

    def another():
        class Dup(Command, body="y"):
            """Second."""

        return Dup

    @p.command
    class Dup(Command, body="x"):
        """First."""

    with refused("TM-M007"):
        p.command(another())


def test_inline_body_line_endings_and_trailing_blank_lines_are_normalised():
    p = pkg()

    @p.command
    class Crlf(Command, body="a\r\nb\r\n\r\n"):
        """Windows line endings."""

    assert "{%\na\nb\n}" in p.render(version="0")


def test_snake_and_generator_version(monkeypatch):
    assert repr(TEXT) == "Text"
    assert snake("FactGap") == "fact_gap" and snake("Name") == "name"
    assert generator_version().count(".") == 2
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "unversioned")
    assert generator_version() == "0.0.0"
