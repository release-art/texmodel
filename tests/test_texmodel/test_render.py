import importlib.metadata
import pathlib
import zipfile

import pydantic
import pytest

from texmodel import drift, package
from texmodel._internal.render import snake
from texmodel.body import TemplateRef
from texmodel.components import Command, Environment
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


def test_fields_are_keyword_only_and_components_are_frozen(acme):
    assert acme.Slot(text="a", label="b").label == "b" and acme.Slot(text="a").label is None
    with pytest.raises(TypeError):
        acme.Slot("a")  # pyright: ignore[reportCallIssue]
    with pytest.raises(pydantic.ValidationError, match="frozen"):
        acme.Slot(text="a").text = "x"  # pyright: ignore[reportAttributeAccessIssue]
    assert acme.Fact(text="x") == acme.Fact(text="x") and hash(acme.Fact(text="x")) == hash(acme.Fact(text="x"))


def test_package_arguments_are_validated():
    for kw, code in (
        ({"name": "Bad Name", "prefix": "t"}, "TM-P001"),
        ({"name": "p", "prefix": "T1"}, "TM-P002"),
        ({"name": "p", "prefix": "t", "date": "2026-10-21"}, "TM-P003"),
    ):
        with refused(code):
            Package(**kw)  # pyright: ignore[reportArgumentType]  # the dict is mixed on purpose


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

    with refused("TM-M037"):

        class TwoOptional(Command):
            """Two optional arguments."""

            a: Text | None = None
            b: Text | None = None

    with refused("TM-M004"):

        class WrongType(Command):
            """A bytes field."""

            n: bytes


def test_a_missing_body_is_an_error_and_files_are_never_found_by_name(tmp_path, monkeypatch):
    p = pkg()
    with refused("TM-M006") as info:

        @p.command
        class NoBody(Command):
            """No body anywhere."""

    assert "body" in str(info.value) and "TemplateRef" in info.value.hint
    # A file called thing.tex beside the class is not picked up: nothing is looked up by name (explicit over implicit).
    (tmp_path / "lonely_mod.py").write_text(
        'from texmodel.components import Command\nclass Thing(Command):\n    """Doc."""\n'
    )
    (tmp_path / "thing.tex").write_text("y")
    monkeypatch.syspath_prepend(str(tmp_path))
    import lonely_mod  # pyright: ignore[reportMissingImports]

    with refused("TM-M006"):
        p.command(lonely_mod.Thing)


def test_a_template_ref_reads_a_file_relative_to_the_defining_module_or_absolute(tmp_path, monkeypatch):
    (tmp_path / "ref_mod.py").write_text(
        "from texmodel.body import TemplateRef\nfrom texmodel.components import Command, Environment\n"
        "class Rel(Command):\n"
        '    """Relative."""\n'
        '    body = TemplateRef("rel.tex")\n'
        "class Meth(Command):\n"
        '    """Method."""\n'
        "    def body(self):\n"
        '        return TemplateRef("sub/meth.tex")\n'
        "class Env(Environment):\n"
        '    """Both ends."""\n'
        '    begin = TemplateRef("env.begin.tex")\n'
        '    end = "\\\\end{center}"\n'
    )
    (tmp_path / "sub").mkdir()
    (tmp_path / "rel.tex").write_text("\\par rel\n")
    (tmp_path / "sub" / "meth.tex").write_text("meth")
    (tmp_path / "env.begin.tex").write_text("\\begin{center}\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    import ref_mod  # pyright: ignore[reportMissingImports]

    p = pkg()
    for cls in (ref_mod.Rel, ref_mod.Meth):
        p.command(cls)
    p.environment(ref_mod.Env)
    text = p.render(version="0.1.0")
    assert "(body: rel.tex)\n\\newcommand{\\tRel}{%\n\\par rel\n}" in text
    assert "(body: meth.tex)" in text and "(body: env.begin.tex + inline)" in text
    absolute = tmp_path / "rel.tex"

    class Abs(Command):
        """Absolute."""

        body = TemplateRef(absolute)

    assert p.command(Abs) is Abs and "\\par rel" in p.render(version="0.1.0")


def test_a_template_ref_is_read_from_a_zip_on_the_path(tmp_path, monkeypatch):
    archive = tmp_path / "decl.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(
            "zipped_mod.py",
            "from texmodel.body import TemplateRef\nfrom texmodel.components import Command\n"
            'class Rel(Command):\n    """Relative."""\n    body = TemplateRef("zipped.tex")\n',
        )
        z.writestr("zipped.tex", "\\par zipped")
    monkeypatch.syspath_prepend(str(archive))
    import zipped_mod  # pyright: ignore[reportMissingImports]

    p = pkg()
    p.command(zipped_mod.Rel)
    assert "\\par zipped" in p.render(version="0.1.0")


def test_a_template_ref_to_a_missing_file_is_refused_when_the_class_is_defined():
    with refused("TM-M005") as info:

        class Gone(Command):
            """No such file."""

            body = TemplateRef("does_not_exist.tex")

    assert "does_not_exist.tex" in str(info.value)


def test_body_lints():
    p = pkg()
    with refused("TM-M009"):

        @p.command
        class Unknown(Command):
            """Hole is not a field."""

            body = "#nope"

            text: Text

    with refused("TM-M008"):

        @p.command
        class Digit(Command):
            """Numbered hole."""

            body = "#1"

            text: Text

    with refused("TM-M010"):

        @p.command
        class Forgot(Command):
            """Never uses its argument."""

            body = "x"

            text: Text

    with refused("TM-M011"):

        @p.command
        class Stray(Command):
            """Closes what was never opened."""

            body = "}#text"

            text: Text

    with refused("TM-M011"):

        @p.command
        class Open(Command):
            """Unbalanced."""

            body = "{#text"

            text: Text

    @p.command
    class Ok(Command, unused=()):
        """Escaped braces and a comment brace are fine."""

        body = "\\{ #text \\} % { comment"

        text: Text

    @p.command
    class Skips(Command, unused=("text",)):
        """Declares the argument unused."""

        body = "x"

        text: Text

    @p.command
    class Hash(Command):
        """A literal # is written ##."""

        body = "##\\par #text"

        text: Text

    assert "##\\par #1" in p.render(version="0")


def test_a_name_collision_is_an_error_at_registration():
    p = pkg()

    def another():
        class Dup(Command):
            """Second."""

            body = "y"

        return Dup

    @p.command
    class Dup(Command):
        """First."""

        body = "x"

    with refused("TM-M007"):
        p.command(another())


def test_inline_body_line_endings_and_trailing_blank_lines_are_normalised():
    p = pkg()

    @p.command
    class Crlf(Command):
        """Windows line endings."""

        body = "a\r\nb\r\n\r\n"

    assert "{%\na\nb\n}" in p.render(version="0")


def test_snake_and_generator_version(monkeypatch):
    assert repr(TEXT) == "Text"
    assert snake("FactGap") == "fact_gap" and snake("Name") == "name"
    assert generator_version().count(".") == 2
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "unversioned")
    assert generator_version() == "0.0.0"


def test_a_generator_version_constant_is_read_before_the_installed_metadata(monkeypatch):
    def no_metadata(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", no_metadata)
    monkeypatch.setattr(package, "GENERATOR_VERSION", "2.3.4.dev5+local")
    assert generator_version() == "2.3.4"


def test_a_body_attribute_is_dedented_and_trimmed_so_a_triple_quoted_string_reads_as_it_renders():
    p = pkg()

    @p.command
    class Title(Command):
        """A title."""

        text: Text
        body = r"""
            \par\noindent
              {\bfseries #text}\par
        """

    @p.environment
    class Box(Environment):
        """A box."""

        begin = r"""
            \begin{center}
        """
        end = "\\end{center}"

    text = p.render(version="0.1.0")
    assert "\\newcommand{\\tTitle}[1]{%\n\\par\\noindent\n  {\\bfseries #1}\\par\n}\n" in text
    assert "\\newenvironment{tBox}{%\n\\begin{center}\n}{%\n\\end{center}\n}" in text


def test_a_body_must_be_a_string_and_a_field_named_body_is_a_field():
    with refused("TM-M021"):

        class NotText(Command):
            """Body is a number."""

            body = 3  # pyright: ignore[reportAssignmentType]

    p = pkg()
    with refused("TM-M006"):  # `body` is the argument here, so there is still no body

        @p.command
        class Field(Command):
            """Has a field called body."""

            body: Text


def test_a_method_can_return_the_body_and_cannot_depend_on_an_instance():
    p = pkg()

    @p.command
    class Aside(Command):
        """Method body."""

        tex: Text

        def body(self):
            return r"""
                \par{\footnotesize #tex}\par
            """

    @p.environment
    class Box(Environment):
        """Methods for both ends."""

        def begin(self):
            return r"\begin{center}"

        def end(self):
            return r"\end{center}"

    text = p.render(version="0.1.0")
    assert "\\newcommand{\\tAside}[1]{%\n\\par{\\footnotesize #1}\\par\n}" in text
    assert "\\newenvironment{tBox}{%\n\\begin{center}\n}" in text
    with refused("TM-M022") as info:

        class UsesSelf(Command):
            """The body reads an instance."""

            text: Text

            def body(self):
                return self.text

    assert "cannot use self" in info.value.hint
    with refused("TM-M021"):

        class NotAString(Command):
            """The method returns a number."""

            def body(self):
                return 3
