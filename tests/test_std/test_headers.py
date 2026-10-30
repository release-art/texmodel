"""The standard-library headers (`texmodel.std`): they load, they are complete, and real TeX accepts a call of each.

The conformance test compiles, per package, a document that loads the package and calls every command and
environment the header declares, with plausible arguments, in the reference image (or, for a package the image lacks,
on this machine's TeX). A name that does not exist, or arguments TeX refuses, fail with the plan path of the call. What
it cannot see is a declared optional argument that the real command does not take: that is for the manual review of a
header.
"""

import importlib
import os
import pathlib
import re
import shutil
import struct
import zlib

import pytest
from test_texmodel_run.test_compile_tex import compiler, fonts  # noqa: F401

from texmodel.body import Hole
from texmodel.components import Command, Passthrough
from texmodel.document import Document
from texmodel.interface import ColourName
from texmodel.package import Package
from texmodel.preamble import PreambleSlots
from texmodel.run.compiler import Compiler
from texmodel.run.diagnostics import PackageError, Severity
from texmodel.std import MODULES, TEXLIVE
from texmodel.types import Length, Raw, Text


def header(name: str):  # noqa: ANN201
    return importlib.import_module(f"texmodel.std.{name}")


def body_of(*lines: str) -> Passthrough:
    return Passthrough(Raw("\n".join(lines)))


# --- static ------------------------------------------------------------------------------------------------------


def test_the_modules_listed_are_the_modules_there_are():
    folder = pathlib.Path(importlib.import_module("texmodel.std").__file__ or "").parent
    assert sorted(p.stem for p in folder.glob("*.py") if p.stem != "__init__") == sorted(MODULES)
    assert TEXLIVE.isdigit()


@pytest.mark.parametrize("name", MODULES)
def test_a_header_is_an_adopted_package_whose_components_all_name_their_control_sequence(name):
    package = header(name).package
    assert isinstance(package, Package) and package.adopted and package.prefix == ""
    assert package.name == (name.replace("_", "-") if name != "latex" else "latex")
    assert package.builtin == (name == "latex")
    for cls in package.registered:
        assert cls.__doc__ and cls.__dict__["cs"] and cls.__tm_cs__ == cls.__dict__["cs"]  # pyright: ignore[reportAttributeAccessIssue]
    if name in {"hyphenat", "anyfontsize"}:
        assert package.registered == ()  # loaded with Package.require; nothing to call


def test_a_body_that_calls_a_header_requires_its_package_and_a_builtin_one_requires_nothing():
    from texmodel.std import graphicx, latex

    pkg = Package("std-user", prefix="su")

    @pkg.command
    class Photo(Command):
        """A picture of the full width."""

        path: Text

        def body(self):
            yield latex.Centering.call()
            yield graphicx.IncludeGraphics.call(
                Hole("path"), options=graphicx.IncludeGraphicsOptions(width=Length.expr(r"\linewidth"))
            )

    sty = pkg.render()
    assert r"\RequirePackage{graphicx}" in sty and "RequirePackage{latex}" not in sty
    assert "\\centering\n\\includegraphics[width=\\linewidth]{#1}" in sty


# --- the samples: one call of every declared name -----------------------------------------------------------------

X = Raw("x")


def latex_samples():
    from texmodel.std import latex as k

    length, counter, box = Raw(r"\tmlen"), Raw("tmc"), Raw(r"\tmbox")
    value = Raw(k.CounterValue(name=counter).render())
    pre = [
        k.DeclareOption(option=Raw("tmopt"), code=Raw("")),
        k.PassOptionsToPackage(options=Raw("final"), package=Raw("microtype")),
    ]
    nodes = [
        k.NewLength(length=length),
        k.SetLength(length=length, value=Length("3mm")),
        k.AddToLength(length=length, value=Length("1mm")),
        k.SetToWidth(length=length, text=Raw("abc")),
        k.SetToHeight(length=length, text=Raw("abc")),
        k.SetToDepth(length=length, text=Raw("abc")),
        k.NewCounter(name=counter),
        k.SetCounter(name=counter, value=Raw("3")),
        k.StepCounter(name=counter),
        k.SetCounter(name=counter, value=value),
        k.Arabic(name=counter),
        k.VSpace(length=Length("1mm")),
        k.HSpace(length=Length("1mm")),
        k.VSpace(starred=True, length=Length("1mm")),
        k.HSpace(starred=True, length=Length("1mm")),
        k.MakeBox(text=Raw("x")),
        k.MakeBox(text=Raw("x"), width=Length("3cm")),
        k.MakeBox(text=Raw("x"), width=Length("3cm"), align=k.BoxAlign.CENTRE),
        k.RaiseBox(lift=Length("1pt"), text=Raw("x")),
        k.RaiseBox(lift=Length("1pt"), text=Raw("x"), height=Length("2pt"), depth=Length("1pt")),
        k.Section(title="S"),
        k.Section(title="S", starred=True),
        k.Section(title="S", short="s"),
        k.Subsection(title="S", starred=True, short="s"),
        k.Subsubsection(title="S"),
        k.NoIndent(),
        k.Par(),
        k.NewPage(),
        k.ThisPageStyle(style=Raw("empty")),
        k.PageStyle(style=Raw("plain")),
        k.Null(),
        k.IgnoreSpaces(),
        k.FrenchSpacing(),
        k.FontSize(size=Raw("10pt"), skip=Raw("12pt")),
        k.SelectFont(),
        k.Bfseries(),
        k.Centering(),
        k.Tiny(),
        k.ScriptSize(),
        k.FootnoteSize(),
        k.Small(),
        k.NormalSize(),
        k.Large(),
        k.LargeCap(),
        k.LargeAllCaps(),
        k.Huge(),
        k.HugeCap(),
        k.TextBold(text="x"),
        k.TextItalic(text="x"),
        k.Emph(text="x"),
        k.MakeUppercase(text="x"),
        k.FpEval(expr=Raw("round(3*2.5, 1)")),
        k.Phantom(text=X),
        k.VPhantom(text=X),
        k.TextBullet(),
        k.TextQuoteLeft(),
        k.TextQuoteRight(),
        k.TextQuoteDblLeft(),
        k.TextQuoteDblRight(),
        k.NewSaveBox(box=box),
        k.UseBox(box=box),
        k.AtBeginDocument(code=Raw("")),
        k.AtEndDocument(code=Raw("")),
        k.PackageWarning(package=Raw("tmpkg"), message=Raw("a warning")),
        k.PackageWarningNoLine(package=Raw("tmpkg"), message=Raw("a warning")),
        k.PackageInfo(package=Raw("tmpkg"), message=Raw("a note")),
        k.IfFileExists(file=Raw("tm-nonexistent.tex"), yes=Raw(""), no=Raw("")),
        k.InputIfFileExists(file=Raw("tm-nonexistent.tex"), yes=Raw(""), no=Raw("")),
        k.Center(body_of("x")),
        k.FlushLeft(body_of("x")),
        k.FlushRight(body_of("x")),
        k.Minipage(body_of("x"), width=Length("3cm"), position=k.BoxPosition.TOP),
        k.ClearPage(),
    ]
    return pre, nodes


def graphicx_samples():
    from texmodel.std import graphicx as g

    return [], [
        g.GraphicsPath(directories=Raw("{}{img/}")),
        g.IncludeGraphics(
            path=Raw("tm-pic.png"),
            options=g.IncludeGraphicsOptions(
                width=Length("1cm"),
                height=Length("1cm"),
                keepaspectratio=True,
                scale=0.5,
                angle=0,
                clip=True,
                extra=Raw("trim=0 0 0 0"),
            ),
        ),
        g.IncludeGraphics(path=Raw("tm-pic.png")),
    ]


def xcolor_samples():
    from texmodel.std import xcolor as c

    return [], [
        c.DefineColor(name=Raw("tmink"), model=Raw("HTML"), spec=Raw("223344")),
        c.ColorLet(name=Raw("tmb"), spec=Raw("tmink!50")),
        c.Color(name=Raw("tmink")),
        c.Color(name=Raw("1,0,0"), model=Raw("rgb")),
        c.TextColor(name=Raw("tmink"), text="x"),
        c.TextColor(name=Raw("1,0,0"), text="x", model=Raw("rgb")),
    ]


def geometry_samples():
    from texmodel.std import geometry as g

    return [
        g.Geometry(
            options=g.GeometryOptions(a4paper=True, margin=Length("10mm"), includehead=True, extra=Raw("heightrounded"))
        )
    ], []


def etoolbox_samples():
    from texmodel.std import etoolbox as e

    macro = Raw(r"\tmm")
    pre = [
        Raw(r"\newcommand{\tmm}{}"),
        e.NewToggle(name=Raw("tmt")),
        e.AtBeginEnvironment(environment=Raw("center"), code=Raw("")),
        e.AtEndEnvironment(environment=Raw("center"), code=Raw("")),
    ]
    nodes = [
        e.Appto(macro=macro, code=X),
        e.GAppto(macro=macro, code=X),
        e.Preto(macro=macro, code=X),
        e.GPreto(macro=macro, code=X),
        e.IfBlank(argument=Raw(""), yes=Raw("a"), no=Raw("b")),
        e.IfStrEqual(first=Raw("a"), second=Raw("a"), yes=Raw("y"), no=Raw("n")),
        e.ToggleTrue(name=Raw("tmt")),
        e.ToggleFalse(name=Raw("tmt")),
        e.SetToggle(name=Raw("tmt"), value=Raw("true")),
        e.IfToggle(name=Raw("tmt"), yes=Raw("y"), no=Raw("n")),
        e.IfNumGreater(left=Raw("2"), right=Raw("1"), yes=Raw("y"), no=Raw("n")),
        e.IfNumLess(left=Raw("1"), right=Raw("2"), yes=Raw("y"), no=Raw("n")),
        e.IfNumEqual(left=Raw("1"), right=Raw("1"), yes=Raw("y"), no=Raw("n")),
    ]
    return pre, nodes


def eso_pic_samples():
    from texmodel.std import eso_pic as p

    at = "".join(c(code=Raw("")).render() for c in (p.AtPageLowerLeft, p.AtPageUpperLeft, p.AtPageCenter))
    return [], [p.AddToShipoutPictureBG(code=Raw(at)), p.AddToShipoutPictureFG(code=Raw(""))]


def microtype_samples():
    from texmodel.std import microtype as m

    return [m.SetProtrusion(set=Raw("encoding=*"), list=Raw("A={50,50}"), options=Raw("name=tmset"))], [
        m.MicrotypeSetup(options=Raw("protrusion=true"))
    ]


def pdfrender_samples():
    from texmodel.std import pdfrender as p

    return [], [p.PdfRender(options=Raw("TextRenderingMode=2,LineWidth=0.4pt"))]


def enumitem_samples():
    from texmodel.std import enumitem as e

    return [], [e.SetList(options=Raw("noitemsep"), lists=Raw("itemize")), e.SetList(options=Raw("noitemsep"))]


def adjustbox_samples():
    from texmodel.std import adjustbox as a

    return [], [
        a.AdjustBox(
            options=a.AdjustBoxOptions(
                max_width=Length.expr(r"\linewidth"),
                center=True,
                valign=a.VAlign.TOP,
                frame=True,
                margin=Length("1mm"),
                scale=0.5,
            ),
            content=Raw("x"),
        )
    ]


def tikz_samples():
    from texmodel.std import tikz as t

    return [
        t.UseTikzLibrary(libraries=Raw("calc,positioning")),
        t.TikzSet(options=t.TikzOptions(extra=Raw("tmstyle/.style={draw}"))),
    ], [
        t.Tikzpicture(
            body_of(r"\draw (0,0) -- (1,1);"),
            options=t.TikzOptions(
                scale=1,
                thick=True,
                draw=ColourName("red"),
                line_width=Length("1pt"),
                rounded_corners=True,
                extra=Raw("->"),
            ),
        ),
        t.Tikzpicture(body_of(r"\node {x};")),
    ]


def tcolorbox_samples():
    from texmodel.std import tcolorbox as t

    return [
        t.TcbUseLibrary(libraries=Raw("skins,fitting")),
        t.TcbSet(options=t.TcolorboxOptions(colback=ColourName("white"))),
    ], [
        t.Tcolorbox(
            body_of("x"),
            options=t.TcolorboxOptions(
                colback=ColourName("white"),
                colframe=ColourName("black"),
                boxrule=Length("0.5pt"),
                arc=Length("1mm"),
                sharp_corners=True,
            ),
        ),
        t.Tcolorbox(body_of("x")),
        t.Tcbox(text=Raw("x"), options=t.TcolorboxOptions(colback=ColourName("white"), opacityback=0.5)),
        t.Tcbox(text=Raw("x")),
    ]


def fontspec_samples():
    from texmodel.std import fontspec as f

    return [
        f.SetMainFont(font=Raw("Latin Modern Roman"), options=Raw("Ligatures=TeX")),
        f.SetSansFont(font=Raw("Latin Modern Sans")),
        f.SetMonoFont(font=Raw("Latin Modern Mono")),
    ], []


def calc_samples():
    from texmodel.std import (
        calc as c,
        latex as k,
    )

    counter, length, box = Raw("tmc"), Raw(r"\tmlen"), Raw(r"\tmtotal")
    pre = [k.NewCounter(name=counter), k.NewLength(length=length), k.NewLength(length=box)]
    return pre, [
        c.SetCounter(counter=counter, value=c.integer(7) / 2),
        c.AddToCounter(counter=counter, value=c.integer(2) * c.real(1.6)),
        c.SetLength(length=length, value=c.widthof("abc") * c.real(0.5) + Length("1pt")),
        c.AddToLength(length=length, value=c.glue(Length("1pt"), Length("1pt"))),
        c.SetToTotalHeight(length=box, text=Raw("Ag")),
    ]


SAMPLES = {
    "latex": latex_samples,
    "graphicx": graphicx_samples,
    "xcolor": xcolor_samples,
    "geometry": geometry_samples,
    "etoolbox": etoolbox_samples,
    "eso_pic": eso_pic_samples,
    "microtype": microtype_samples,
    "hyphenat": lambda: ([], []),
    "anyfontsize": lambda: ([], []),
    "calc": calc_samples,
    "pdfrender": pdfrender_samples,
    "enumitem": enumitem_samples,
    "adjustbox": adjustbox_samples,
    "tikz": tikz_samples,
    "tcolorbox": tcolorbox_samples,
    "fontspec": fontspec_samples,
}
ERRORS = {"PackageError"}  # declared and called in `test_package_error`: it stops the run on purpose


def rendered(name: str) -> str:
    pre, nodes = SAMPLES[name]()
    return "\n".join(n.render() if not isinstance(n, Raw) else n.tex for n in [*pre, *nodes])


def test_every_sample_set_is_listed_and_calls_every_declared_name():
    assert set(SAMPLES) == set(MODULES)
    for name in MODULES:
        text = rendered(name)
        for cls in header(name).package.registered:
            cs = cls.__dict__["cs"]
            if cs in ERRORS:
                continue
            assert re.search(rf"\\{cs}(?![A-Za-z])|\\begin\{{{cs}\}}", text), f"{name}: no sample calls {cs}"


# --- conformance: real TeX accepts the calls --------------------------------------------------------------------


def png() -> bytes:
    """A 1x1 white picture, so graphicx has a file to place."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
        + chunk(b"IEND", b"")
    )


GAP = ("TM-X013", "did not find the tikz library")  # what a TeX Live that is smaller than the deck's looks like


def host_compiler() -> Compiler | None:
    if shutil.which("lualatex") and shutil.which("latexmk"):
        return Compiler(epoch=1700000000, timeout=300)
    return None


async def compile_sample(comp: Compiler, plan, tmp_path: pathlib.Path):  # noqa: ANN001, ANN201
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "d.tex").write_text(plan.text, encoding="utf-8")
    (src / "tm-pic.png").write_bytes(png())
    result = await comp.compile(src / "d.tex", tmp_path / "out", plan=plan)
    errors = [d for d in result.diagnostics if d.severity is Severity.ERROR]
    return result, errors, [d for d in errors if d.code == GAP[0] or GAP[1] in d.message]


@pytest.mark.tex
@pytest.mark.timeout(900)
@pytest.mark.parametrize("name", MODULES)
async def test_real_tex_accepts_a_call_of_every_declared_name(name, compiler, tmp_path):  # noqa: F811
    """In the reference image. If the image lacks a file the sample needs, the run is skipped with what is missing, or
    repeated on this machine's TeX when TEXMODEL_STD_ON_HOST=1; any other error fails with the plan path of the call."""
    from texmodel.std import latex

    package = header(name).package
    pre, nodes = SAMPLES[name]()
    slots = PreambleSlots(after_package=tuple(n if isinstance(n, Raw) else Raw(n.render()) for n in pre))
    plan = package.plan(Document(*nodes, latex.Null(), preamble=slots))
    result, errors, gaps = await compile_sample(compiler, plan, tmp_path)
    if gaps and len(gaps) == len(errors):
        host = host_compiler() if os.environ.get("TEXMODEL_STD_ON_HOST") else None
        if host is None:
            pytest.skip(f"the reference image lacks: {sorted({d.message for d in gaps})}")
        result, errors, gaps = await compile_sample(host, plan, tmp_path / "host")
    assert result.ok and not errors, [(d.path, d.code, d.message) for d in errors]


@pytest.mark.tex
@pytest.mark.timeout(300)
async def test_package_error_is_the_error_it_says(compiler, tmp_path):  # noqa: F811
    from texmodel.std import latex

    node = latex.PackageError(package=Raw("tmpkg"), message=Raw("it broke"), help=Raw("press return"))
    plan = latex.package.plan(node)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "d.tex").write_text(plan.text, encoding="utf-8")
    result = await compiler.compile(tmp_path / "src" / "d.tex", tmp_path / "out", plan=plan)
    (found,) = (d for d in result.diagnostics if isinstance(d, PackageError))
    assert (found.package, found.message, found.path) == ("tmpkg", "it broke.", "PackageError[0]")


def test_without_lualatex_there_is_no_host_compiler(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert host_compiler() is None
