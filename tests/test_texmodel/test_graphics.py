"""`texmodel.ext.graphics`: pictures with opinions, and the figure that holds one."""

import os
from pathlib import PurePosixPath

import pytest
from test_std.test_headers import compile_sample, host_compiler
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel._internal.read import detokenized
from texmodel.document import Document
from texmodel.errors import ValidationError
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
        with pytest.raises(ValidationError) as caught:
            Picture("a.png", **kwargs)
        assert caught.value.code == "TM-C033"


def test_a_scale_excludes_a_width_or_a_height():
    with pytest.raises(ValidationError) as caught:
        Picture("a.png", alt="x", scale=2, height=Length("1cm"))
    assert caught.value.code == "TM-C034"


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
    with pytest.raises(ValidationError) as caught:
        Figure(Picture("a.png", alt="x"), placement="x")
    assert caught.value.code == "TM-C035"


PICTURES = [
    Picture("a.png", alt="x"),
    Picture("img/a_b.png", decorative=True, scale=0.5, rotate=90, page=2),
    Picture("a.png", alt="A, B = {c} 100% & $", width=Length("3cm"), height=Length.expr(r"0.5\linewidth")),
    Picture("a.png", alt="Cut", crop=Crop(Length("1mm"), Length("0pt"), Length("2cm"), Length("3pt"))),
]


@pytest.mark.parametrize("picture", PICTURES)
def test_a_picture_reads_back_from_the_call_it_was_written_as(picture):
    assert Picture.from_tex(detokenized(picture.render())) == picture
    assert Picture.from_tex("{" + detokenized(picture.render()) + "}") == picture


@pytest.mark.parametrize(
    "text",
    [
        "no picture",
        r"\includegraphics [alt=x,bleed=3mm]{a.png}",
        r"\includegraphics [width,alt=x]{a.png}",
        r"\includegraphics [width=wide,alt=x]{a.png}",
        r"\includegraphics {a.png}",  # neither alt nor decorative
        r"\includegraphics [alt=x]{a}b.png}",
        r"\includegraphics [alt=x]{a%b.png}",
    ],
)
def test_a_call_that_is_no_picture_is_refused_with_the_reason(text):
    with pytest.raises(ValueError):  # noqa: PT011
        Picture.from_tex(text)


def test_a_path_from_a_macro_is_not_read():
    with pytest.raises(NotImplementedError):
        Picture.from_tex(r"\includegraphics [alt=x]{\figdir a}")


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
