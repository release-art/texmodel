# Standard libraries

`texmodel.std` has a typed header for each TeX package a deck loads: `latex` (the kernel), `graphicx`, `xcolor`, `geometry`,
`etoolbox`, `eso_pic`, `microtype`, `hyphenat`, `anyfontsize`, `calc`, `pdfrender`, `enumitem`, `adjustbox`, `tikz`,
`tcolorbox`, `fontspec`, `tabularray`, `hyperref`, `setspace`, `fancyhdr`, `caption`, `subcaption`, `babel`,
`polyglossia`, `multicol`, `pdfpages`, `luacolor`, `beamer` and `pgfplots`. The blocks on this page run in order, as one module.

A header is an adopted package with no prefix, whose components name their TeX command with `cs`:

```py
class IncludeGraphics(Command):
    r"""Place a picture: `\includegraphics[width=3cm]{a.png}`."""

    cs = "includegraphics"
    path: Raw
    options: IncludeGraphicsOptions | None = None    # a KeyVals: TeX's one optional argument, written first
```

## Using a header

A body that calls a header's component makes the generated `.sty` load that package. The kernel header (`builtin=True`)
never does.

```python
from texmodel.body import Hole
from texmodel.components import Command
from texmodel.package import Package
from texmodel.std.graphicx import IncludeGraphics, IncludeGraphicsOptions
from texmodel.types import Length, Raw

pkg = Package("figures", prefix="fg")


@pkg.command
class Figure(Command):
    """A full-width picture."""

    path: Raw

    def body(self):
        yield IncludeGraphics.call(
            Hole("path"), options=IncludeGraphicsOptions(width=Length.expr(r"\linewidth"))
        )


assert r"\RequirePackage{graphicx}" in pkg.render()
```

A library whose commands no body calls, or that takes options, is loaded with `pkg.require`, before the packages the bodies
need:

```python
from texmodel.std import microtype

pkg.require(microtype.package, options=["protrusion=true"])
assert r"\RequirePackage[protrusion=true]{microtype}" in pkg.render()
```

## What is typed

`adjustbox`, `graphicx`, `geometry`, `microtype`, `tcolorbox`, `tikz` and `tabularray` type their key lists. `Raw` is the last resort in a header: it stays for content that is TeX and a key list's `extra`. `calc` is a typed expression language:
`dimen(Length("2cm")) * real(0.5) + widthof("abc")`, with `maxof`, `minof`, `ratio`, `glue`, `integer` and `counter_value`.
The kernel types `\vspace*`, `\makebox`, `\raisebox` and the sectioning commands. `tabularray` types the whole of the package and its `booktabs`, `diagbox` and `tikz` libraries, and `TableRow`, the base of a package's own rows ([Tables](tables.md#rows-that-are-nodes)): the inner and outer key lists,
the commands inside a table and the definers. A key that carries arguments (`cell{1}{2}`, `hline{1,Z}`, `note{a}`) is an
`Entry` built by `cell(1, 2, CellSpec(...))`, `hline(selector(1, "Z"), HlineSpec(...))`, `note(...)`; `selector` checks
an index, a range or `odd`/`even`/`every`. `colspec` and `rowspec` stay `Raw`, and cells are TeX between `Passthrough`s.
A library's own syntax (TikZ paths such
as `\draw (0,0) -- (1,1);`) is written as `Passthrough` or `Raw`.

`tests/test_std` compiles a call of every declared name against the reference image, so a header that names a command TeX
does not have fails, with the path of the call.

`beamer` is a class, not a package: it is `builtin` (a call requires nothing) and the deck's package says
`Package(..., document_class="beamer")`; class options (`aspectratio=169`) are the document's `options`. An overlay
specification is an `overlay` field of `Text`, written in `<>` before the other arguments (`Frame(..., overlay="2-")` is
`\begin{frame}<2->`); `Gap.OMIT` lets it be left out before `[options]`. Inserts (`\insertframenumber`) are written in a
template's code, so they are not declared.

`ltx_talk` is beamer's replacement for a deck that needs `\DocumentMetadata` (PDF/A, PDF/X, tagging): beamer refuses it, so a
document with `metadata` or `pdf` for a package whose class is beamer is `TM-C050`. The class needs `\DocumentMetadata` itself,
so the plan always writes one (empty unless `metadata` or `pdf` say more): `Package(metadata=MetadataPolicy.REQUIRED)`; beamer says
`REFUSED`, every other class `ALLOWED`. Class options are typed (`TalkOptions` gives the `options` of a document, `AspectRatio(4, 3)` is
`4:3`). The package always passes `frame-title-arg=true` (`Package(class_options=)`), so a `Frame` always writes its title
argument, `{}` when it has none: the class reads the argument as text of the frame otherwise. A `Frame`, a `Block` and the overlay
environments take any command or environment (a deck's own too). `MakeTitle` goes inside a `Frame`. The styling is `\EditInstance`, one command for the
class's templates: `template` says which and `keys` is that template's keys class, or `TM-C049`.

```python
from texmodel.components import Passthrough
from texmodel.document import Document
from texmodel.interface import ColourName
from texmodel.preamble import RequireMetadata
from texmodel.std import ltx_talk as talk
from texmodel.types import Name, Raw

deck = Document(
    talk.EditInstance(
        template=talk.Template.FOOTER,
        instance=Name("std"),
        keys=talk.FooterKeys(color=ColourName("white"), element_order=(talk.FooterElement.TITLE, talk.FooterElement.FRAME_NUMBER)),
    ),
    talk.Frame(Passthrough(Raw("Hello")), title="Hi"),
    options=talk.TalkOptions(aspect_ratio=talk.AspectRatio(4, 3)).options(),
    metadata=RequireMetadata(lang="en-GB"),
)
tex = talk.package.document(deck)
assert r"\documentclass[frame-title-arg=true,aspect-ratio=4:3]{ltx-talk}" in tex
assert r"\EditInstance{footer}{std}{color=white,element-order={title,framenumber}}" in tex
```

The class is experimental (ltx-talk 0.4, "design support is lower priority"), so its template names may move: this header is where
that shows. It loads a New Computer Modern font; the test image installs `newcomputermodern`.

`fontspec` types its font options (`FontOptions`: the files of the faces, `Scale`, `Ligatures`, `Numbers`, ...) and declares
`NewFontFamily`, `NewFontFace`, `FontSpec`, `AddFontFeatures` and `DefaultFontFeatures` besides `SetMainFont`. A call that
should run when your package loads goes in `Package.at_load`, after the packages it `require`s:

```py
from texmodel.std import fontspec

pkg = Package("acfonts", prefix="ac")
pkg.require(fontspec.package)
pkg.at_load("fonts", fontspec.SetMainFont(font=FontName("Skolar.otf"), options=fontspec.FontOptions(
    upright_font=FontName("Skolar.otf"), bold_font=FontName("Skolar-Bold.otf"))))
```

A value a header takes is a type, not TeX: `fancyhdr.Places(("LE", "RO"))`, `pdfpages.PageRanges(("1-3", "last"))` and `Nup(2, 1)`,
`graphicx.Trim(left=Length("1cm"))`, `enumitem.ListOptions` and `caption.CaptionOptions`. One that refuses its value raises a
`ValueRuleError` with a code (`TM-C037` to `TM-C047`), which is also a `ValueError`.

`xcolor` takes a colour as a `ColourSpec`: `ColourSpec.named(ColourName("ink", tint=0.5))`, or components with the model they
belong to (`Color(spec=ColourSpec.of(1, 0, 0), model=ColourModel.RGB_UNIT)`); a model and spec that do not fit are `TM-C036`.

`pgfplots` has the axis environments (inside a `tikz.Tikzpicture`), `PgfplotsSet` and `PgfplotsCreatePlotCycleList`;
`Colormap` and `CycleList` write a colour map and a cycle list: a map's stops are triples of 0 to 255 or colours by name
(`ColourName("ra-seq-1")`, a registered colour value), which follow the colour's definition and so the `cmyk` model. Cycle
list and colour map names are `PlotName`s, which may have spaces (`PlotName("ra brand")`). To use it only when the document loads the package, wrap the
calls in `latex.IfPackageLoadedT` inside `latex.AtBeginDocument`.
