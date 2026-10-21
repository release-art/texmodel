"""The compile suite (V3): the real driver, latexmk and LuaTeX in the reference image.

Skipped without Docker and an image that has latexmk; TEXMODEL_REQUIRE_TEX=1 (CI) makes that a failure (V5).
The image comes from TEXMODEL_TEST_IMAGE, else `[tool.texmodel] image`.
"""

import os
import pathlib
import shutil
import tomllib

import pytest

from texmodel import diagnostics as d
from texmodel.compiler import Compiler
from texmodel.errors import ToolchainError

TEX = pathlib.Path(__file__).parent.parent / "fixtures" / "tex"
ROOT = pathlib.Path(__file__).parents[2]

pytestmark = [pytest.mark.tex, pytest.mark.timeout(300)]


def _image() -> str:
    if image := os.environ.get("TEXMODEL_TEST_IMAGE"):
        return image
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["texmodel"]["image"]


@pytest.fixture(scope="session")
def fonts(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    return tmp_path_factory.mktemp("fonts")


@pytest.fixture
def compiler(fonts: pathlib.Path) -> Compiler:
    comp = Compiler(image=_image(), font_cache=fonts, epoch=1700000000)
    try:
        comp.check_ready()
    except ToolchainError as exc:
        if os.environ.get("TEXMODEL_REQUIRE_TEX"):
            pytest.fail(f"reference image unusable: {exc}")
        pytest.skip(f"no usable reference image: {exc}")
    return comp


def doc(tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    (tmp_path / "src").mkdir(exist_ok=True)
    return pathlib.Path(shutil.copy(TEX / name, tmp_path / "src" / name))


def codes(result) -> set[str]:  # noqa: ANN001
    return {x.code for x in result.diagnostics}


def test_a_clean_document_compiles_in_two_passes_and_reports_the_image(compiler, tmp_path):
    result = compiler.compile(doc(tmp_path, "ok.tex"), tmp_path / "out")
    assert (
        result.ok
        and result.pages == 1
        and result.passes == 2
        and result.pdf
        and result.pdf.read_bytes()[:5] == b"%PDF-"
    )
    assert result.image == compiler.image and result.image_digest and result.latexmk_version
    assert "LuaHBTeX" in result.engine_version
    result.raise_for_status()


def test_real_diagnostics_are_typed(compiler, tmp_path):
    result = compiler.compile(doc(tmp_path, "bad.tex"), tmp_path / "out")
    assert not result.ok
    assert {"TM-X010", "TM-X011", "TM-X012", "TM-X018"} <= codes(result)
    glyph = next(x for x in result.diagnostics if isinstance(x, d.MissingCharacter))
    assert glyph.codepoint in {0x1D538, 0x16A0} and "TeX Gyre Termes" in glyph.font


@pytest.mark.parametrize(
    ("name", "code"),
    [("missing_file.tex", "TM-X013"), ("missing_package.tex", "TM-X013"), ("bad_font.tex", "TM-X014")],
)
def test_fatal_errors_are_explained_not_just_failed(compiler, tmp_path, name, code):
    result = compiler.compile(doc(tmp_path, name), tmp_path / "out")
    assert not result.ok and code in codes(result) and "TM-X099" not in codes(result)


def test_two_builds_in_reproducible_mode_are_byte_identical(compiler, tmp_path):
    src = doc(tmp_path, "ok.tex")
    a = compiler.compile(src, tmp_path / "a")
    b = compiler.compile(src, tmp_path / "b")
    assert a.pdf and b.pdf and a.pdf.read_bytes() == b.pdf.read_bytes()


def test_a_document_that_never_settles_names_the_entries_that_move(compiler, tmp_path):
    comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, max_passes=3)
    result = comp.compile(doc(tmp_path, "unstable.tex"), tmp_path / "out")
    (note,) = [x for x in result.diagnostics if isinstance(x, d.NotConverged)]
    assert note.code == "TM-X030" and result.passes == 3
    assert note.changed and "texmodelrun" in "".join(note.changed)


def test_shell_escape_is_off(compiler, tmp_path):
    # The document asks the shell to create a file in the one writable directory; it must not appear.
    result = compiler.compile(doc(tmp_path, "shell_escape.tex"), tmp_path / "out")
    assert result.ok and not (tmp_path / "out" / "pwned.txt").exists()


def test_asset_roots_are_searched_in_order(compiler, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    for root, word in ((first, "FIRST"), (second, "SECOND")):
        root.mkdir()
        (root / "part.tex").write_text(word)
    src = tmp_path / "src" / "main.tex"
    src.parent.mkdir()
    src.write_text("\\documentclass{article}\\begin{document}\\input{part}\\end{document}")
    comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, roots=(first, second))
    result = comp.compile(src, tmp_path / "out")
    assert result.ok and result.log
    log = result.log.read_text(errors="replace")
    assert "/work/roots/0/part.tex" in log and "/work/roots/1/part.tex" not in log  # container paths, earlier wins


def test_cache_hit_and_clean(compiler, tmp_path):
    comp = Compiler(image=compiler.image, font_cache=compiler.font_cache, cache_dir=tmp_path / "cache")
    src = doc(tmp_path, "ok.tex")
    assert not comp.compile(src, tmp_path / "o1").cache_hit
    hit = comp.compile(src, tmp_path / "o2")
    assert hit.cache_hit and hit.pdf and hit.pdf.is_file()
    comp.clean(src, tmp_path / "o1")
    assert not (tmp_path / "o1" / "ok.aux").exists() and (tmp_path / "o1" / "ok.pdf").exists()
    comp.clean(src, tmp_path / "o1", everything=True)
    assert not (tmp_path / "o1" / "ok.pdf").exists()


def test_recompiling_an_unchanged_document_in_place_is_ok(compiler, tmp_path):
    src = doc(tmp_path, "ok.tex")
    first = compiler.compile(src, tmp_path / "out")
    again = compiler.compile(src, tmp_path / "out")
    assert first.ok and again.ok and again.passes == 0 and again.pdf == first.pdf
