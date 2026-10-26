"""The embedded-font check: the log reader on logs of the shape LuaTeX writes, and one real compile."""

import pathlib
import textwrap

import pytest

from test_texmodel_build.test_compile_tex import compiler, fonts  # noqa: F401
from texmodel_build.fonts import embedded, outside

LOG = textwrap.dedent("""
    ...
     32 fonts using 2958895 bytes
     73i,5n,92p,238b,232s stack positions out of 10000i,1000n,20000p,200000b,200000s
    </usr/share/fonts/lm/lmmono10-regular.otf></usr/share/fonts/lm/lmsans10-regular.otf><./fonts/lmr.otf>
    Output written on a.pdf (1 page, 5902 bytes).
""").strip()


def test_the_fonts_a_log_lists_are_read_in_order_and_resolved_against_the_source_directory(tmp_path):
    assert embedded(LOG, tmp_path) == [
        pathlib.Path("/usr/share/fonts/lm/lmmono10-regular.otf"),
        pathlib.Path("/usr/share/fonts/lm/lmsans10-regular.otf"),
        (tmp_path / "fonts" / "lmr.otf").resolve(),
    ]


def test_a_font_outside_the_allowed_directories_is_reported(tmp_path):
    assert outside(LOG, [tmp_path / "fonts"], tmp_path) == [
        pathlib.Path("/usr/share/fonts/lm/lmmono10-regular.otf"),
        pathlib.Path("/usr/share/fonts/lm/lmsans10-regular.otf"),
    ]
    assert (
        outside(LOG, [pathlib.Path("fonts"), pathlib.Path("/usr/share/fonts")], tmp_path) == []
    )  # a relative directory is the source's


def test_a_listing_that_was_wrapped_is_joined(tmp_path):
    wrapped = LOG.replace("lmsans10-", "lmsans\n10-")
    assert pathlib.Path("/usr/share/fonts/lm/lmsans10-regular.otf") in embedded(wrapped, tmp_path)


def test_a_log_without_a_listing_embeds_nothing(tmp_path):
    assert embedded("! Emergency stop.", tmp_path) == outside("", [], tmp_path) == []


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_a_real_compile_lists_the_fonts_it_embedded(compiler, tmp_path):  # noqa: F811
    source = tmp_path / "f.tex"
    source.write_text(
        "\\documentclass{article}\\usepackage{fontspec}\\setmainfont{TeX Gyre Termes}\n"
        "\\begin{document}Hello\\end{document}\n",
        encoding="utf-8",
    )
    result = compiler.compile(source, tmp_path / "out")
    assert result.ok and result.log
    log = result.log.read_text(encoding="utf-8", errors="replace")
    assert any("termes" in f.name.lower() for f in embedded(log, tmp_path))
    assert outside(log, [tmp_path / "fonts"], tmp_path) == embedded(log, tmp_path)
