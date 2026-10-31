"""`texmodel.ext.graphics`: pictures with opinions, and the figure that holds one."""

import os
from pathlib import PurePosixPath

import pytest
from test_std.test_headers import compile_sample, host_compiler
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.document import Document
from texmodel.errors import DeclarationError, ValidationError
from texmodel.ext.graphics import Crop, Figure, Picture
from texmodel.std import graphicx, latex
from texmodel.types import FilePath, Length


def test_a_picture_fits_its_box_and_keeps_its_proportions():
    box = Picture("a.png", alt="x", width=Length("3cm"), height=Length("2cm"))
    assert box.render() == r"\includegraphics[width=3cm,height=2cm,keepaspectratio,alt=x]{a.png}"
    assert "keepaspectratio" not in Picture("a.png", alt="x", width=Length("3cm")).render()


def test_a_picture_is_cropped_rotated_and_scaled():
    text = Picture("a.png", alt="x", scale=0.5, rotate=90, page=2, crop=Crop(left=Length("1mm"))).render()
    assert text == r"\includegraphics[scale=0.5,angle=90,page=2,clip,trim=1mm 0pt 0pt 0pt,alt=x]{a.png}"


def test_a_picture_says_what_it_shows_or_that_it_is_decoration():
    assert Picture("a.png", decorative=True).render() == r"\includegraphics[artifact]{a.png}"
    assert Picture("a.png", alt="A, B = 100%").render() == r"\includegraphics[alt={A, B = 100\%}]{a.png}"
    for kwargs in ({}, {"alt": "x", "decorative": True}):
        with pytest.raises(DeclarationError) as caught:
            Picture("a.png", **kwargs)
        assert caught.value.code == "TM-M089"


def test_a_scale_excludes_a_width_or_a_height():
    with pytest.raises(DeclarationError) as caught:
        Picture("a.png", alt="x", scale=2, height=Length("1cm"))
    assert caught.value.code == "TM-M090"


def test_a_path_is_a_checked_name_or_one_already():
    expected = r"\includegraphics[alt=x]{img/a.png}"
    for path in ("img/a.png", PurePosixPath("img/a.png"), FilePath("img/a.png")):
        assert Picture(path, alt="x").render() == expected
    with pytest.raises(ValidationError) as caught:
        Picture("a}.png", alt="x").render()
    assert caught.value.code == "TM-C028"


def test_a_figure_centres_its_picture_with_the_caption_below_and_the_label_after():
    figure = Figure(Picture("a.png", alt="x"), caption="A & B", short="AB", label="fig:a", placement="tbp")
    assert figure.render() == (
        "\\begin{figure}[tbp]\n\\centering\n\\includegraphics[alt=x]{a.png}\n\\caption[AB]{A \\& B}\n"
        "\\label{fig:a}\n\\end{figure}"
    )
    assert Figure(Picture("a.png", decorative=True)).render().count("\n") == 3


def test_a_placement_is_float_letters():
    with pytest.raises(DeclarationError) as caught:
        Figure(Picture("a.png", alt="x"), placement="x")
    assert caught.value.code == "TM-M091"


@pytest.mark.tex
@pytest.mark.timeout(900)
async def test_real_tex_sets_the_pictures_and_the_figure(compiler, tmp_path):  # noqa: F811
    pictures = [
        Picture("tm-pic.png", alt="A, B", width=Length("3cm"), height=Length("2cm")),
        Picture("tm-pic.png", decorative=True, scale=2, rotate=90),
        Picture("tm-pic.png", alt="Cut", crop=Crop(), width=Length.expr(r"0.5\linewidth")),
    ]
    nodes = [*(p.node() for p in pictures), Figure(pictures[0], caption="Cap", label="fig:a").node(), latex.Null()]
    plan = graphicx.package.plan(Document(*nodes))
    result, errors, gaps = await compile_sample(compiler, plan, tmp_path)
    if gaps and len(gaps) == len(errors):
        host = host_compiler() if os.environ.get("TEXMODEL_STD_ON_HOST") else None
        if host is None:
            pytest.skip(f"the reference image lacks: {sorted({d.message for d in gaps})}")
        result, errors, gaps = await compile_sample(host, plan, tmp_path / "host")
    assert result.ok and not errors, [(d.path, d.code, d.message) for d in errors]
