# Print output

`texmodel.ext` holds opinionated helpers; two are for a PDF a printer receives. The blocks on this page run in order, as
one module.

## A print page

`PrintPage` is the trim, the bleed past it, the sheet around it for marks, and the margin from the trim to the type area.
It writes the `\geometry` call and the PDF page boxes, edge by edge, as numbers: TeX computes nothing. A page box is
`/TrimBox` (the finished page) and `/BleedBox` (where artwork must run to); PDF/X only asks that they exist and nest, so a
file can be valid and trimmed to the wrong size.

```python
from texmodel.document import Document
from texmodel.ext.intent import OutputCondition, OutputIntent, Standard
from texmodel.ext.printpage import PrintPage, Sheet, Sides
from texmodel.package import Package
from texmodel.types import Length

pkg = Package("acme-print", prefix="ap")
page = PrintPage(
    width=Length("105mm"), height=Length("138mm"),        # the trim
    bleed=Sides(all=Length("3mm"), left=Length("0mm")),   # none on the spine edge
    overflow=Length("7mm"),                               # room for marks; default: the bleed
    margin=Sides(horizontal=Length("7mm"), vertical=Length("1.5mm")),
)
page.declare(pkg)
assert r"\pdfvariable pageattr{/CropBox [0 0 337.32283 430.86614]" in pkg.render()
```

A length for every edge is a `Length`, or `Sides`: `Sides(all=)`, `Sides(horizontal=, vertical=)` or the four edges, where an
edge after `all=` or `horizontal=` and `vertical=` replaces that one. An edge left without a length is `TM-M051`; an
overflow smaller than the bleed on any edge is `TM-M052`.

`sheet=Sheet.TRIM` is a review copy: the sheet is the trim alone and the type area is the same as in `Sheet.FULL`.
`/MediaBox` is the engine's, and is not written (a second one is a duplicate key in every page dictionary). The page is
written once, at declaration: a document does not change it, and the engine must be LuaTeX. Crop marks are not drawn.

## A spot colour

`texmodel.ext.spot` declares a named plate on the press, such as a varnish, a foil or a Pantone, with the process colour a
viewer shows in its place. It is `/Separation /Scodix /DeviceCMYK` in the PDF: the press reads the plate name.

```python
from texmodel.components import Value
from texmodel.ext.kplate import K
from texmodel.ext.spot import Spot, SpotColour, tint


@pkg.value
class Varnish(Value[SpotColour]):
    """Spot-UV varnish."""

    default = Spot("Scodix", proxy=K(1))


assert r"\definespotcolor{ap-varnish}{Scodix}{0,0,0,1}" in pkg.render()
assert tint(Varnish, 0.6) == "ap-varnish!60"      # xcolor's tint: the plate at 60%
```

- A plate name may hold spaces, non-ASCII and most punctuation (`PANTONE 302 C`). A PDF name ends at `/ ( ) < > [ ] { }`,
  and TeX reads `% # \`: a name with one of them writes a file cut in two or none at all, so it is `TM-M053`.
- The package is `colorspace` (the `spotcolor` package is pdfTeX-only), loaded with `xcolor`.
- `colorspace` stops on a plate defined twice, so a spot value is declared once and a document cannot set it (`TM-M055`).
- A tint of a value that is not a spot is `TM-M054`; the proxy is a `CMYK`, bounded like every colour.
- To give a mask only one plate, build it from `K` values and check it with `is_single_plate`
  ([Values](values.md#colours-on-one-plate)).

## An output intent

A PDF/X or PDF/A file names the ICC profile its colours are in. `OutputIntent` writes the `\DocumentMetadata` keys and
registers the profile's output condition. l3pdfmeta knows the condition of two profile names only (`sRGB.icc`,
`FOGRA39L_coated.icc`); for any other it writes no intent, and says only that the colour profile is unknown.

```python
condition = OutputCondition(
    "FOGRA39L_coated.icc", identifier="FOGRA39", info="Coated FOGRA39 (ISO 12647-2:2004)", colorants=4
)
intent = OutputIntent(condition, standards=(Standard.X4, Standard.A2B), language="en-GB", pdf_version="1.7")
intent.declare(pkg, directory="res/icc")
tex = pkg.document(Document(preamble=intent.slots(directory="res/icc")))
assert "colorprofiles={X=res/icc/FOGRA39L_coated.icc,A=res/icc/FOGRA39L_coated.icc}" in tex
assert tex.index(r"\DocumentMetadata") < tex.index(r"\documentclass")
```

- One `\DocumentMetadata` claims every standard, each with an intent of the same condition (`pdfx` cannot claim PDF/X-4
  and PDF/A-2b together). `colorprofiles` is `subtype=path` pairs: the bare file name is a key without a value, and writes
  no intent.
- `declare` registers the profile under the bare name and under `directory/name`: the two spellings a document may reach it by.
- PDF/A-2b is PDF 1.7 at most and the engine writes 2.0 unasked, so a PDF/A-2b intent needs `pdf_version` (`TM-M050`).
- A condition value the TeX kernel would misread (`,`, `=`, `%`, `\`, braces, `#`; a space in the profile) is `TM-M048`;
  `colorants` is 1, 3 or 4 (`TM-M049`).
- `condition.check_profile(path.read_bytes())` reads the file's ICC header: a truncated file or a Git LFS pointer is not a
  profile (`TM-C014`), and a profile of the wrong colour space for `colorants` is `TM-C015`. Whether the file is where the
  compile will look is the compiler's roots, not the library's.
