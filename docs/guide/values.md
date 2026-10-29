# Values and settings

A `Value[T]` is a setting: a length, a colour, a flag, a text or a piece of TeX. Its type decides the declaration, so it
needs no body. The blocks on this page run in order, as one module.

```python
from texmodel.components import Value
from texmodel.document import Document
from texmodel.package import Package, setting_line
from texmodel.types import CMYK, Colour, Length, Raw, Text

pkg = Package("vals", prefix="vl")


@pkg.value
class Gap(Value[Length]):
    """Space under each fact."""

    default = Length("2mm")


@pkg.value
class Ink(Value[Colour]):
    """The text colour."""

    default = CMYK(0, 0, 0, 0.95)


@pkg.value
class Compact(Value[bool]):
    """Tighten the layout."""

    default = False


@pkg.value
class DeckName(Value[Text]):
    """The deck name printed on every card."""

    default = "Untitled"


@pkg.value
class Footer(Value[Raw]):
    """The footer, as TeX."""

    default = Raw(r"\textit{draft}")
```

| `T` | Declaration | A document sets it with |
|---|---|---|
| `Length` | `\newlength{\vlGap}` and `\setlength` | `\setlength{\vlGap}{3mm}` |
| `Colour` | `\definecolor{vl-ink}{cmyk}{...}` | `\definecolor{vl-ink}{...}` |
| `bool` | `\newif\ifvlCompact` | `\vlCompacttrue` / `\vlCompactfalse` |
| `Text` | `\newcommand{\vlDeckName}{Untitled}` | `\renewcommand{\vlDeckName}{R\&D}` |
| `Raw` | `\newcommand{\vlFooter}{...}` | `\renewcommand{\vlFooter}{...}` |

Packages a value needs (`xcolor` for colours) are `\RequirePackage`d once, sorted. A colour's name is `<prefix>-<kebab>`
unless `colour_name` says otherwise. A `cs` gives a value's whole control sequence when it is not prefix plus class name.
A package's own kinds exist too: `texmodel.std.etoolbox.Toggle` is `\newtoggle`.

## Settings for a document

```python
settings = [Gap(Length("3mm")), DeckName("R&D"), Compact(True)]
tex = pkg.document(Document(settings=settings))
assert r"\setlength{\vlGap}{3mm}" in tex
assert r"\renewcommand{\vlDeckName}{R\&D}" in tex
```

Every setting, of any type, is written right after `\usepackage`, in the order given, before the `after_package` entries
and `\begin{document}`. What the package computes in the preamble therefore already sees it. This order is tested.

`setting_line(value)` is the line written for one setting:

```python
assert setting_line(Gap(Length("3mm"))) == r"\setlength{\vlGap}{3mm}"
```

## Plates

A press prints a colour with one or more plates: the process inks C, M, Y and K, or a spot. Small type set on four plates
shows every registration error; on one plate it cannot misregister with itself. A colour value declares the plates it may
ink with `plates`, and a default, a setting or data outside them is refused (`TM-M070`):

```python
from texmodel.ext.plates import K, Plate, plates_of
from texmodel.types import CMYK, Colour


@pkg.value
class TextInk(Value[Colour]):
    """Text ink."""

    plates = {Plate.K}                 # the black plate only; {Plate.C, Plate.M} is a duotone
    default = K(0.95)


assert r"\definecolor{vl-text-ink}{cmyk}{0,0,0,0.95}" in pkg.render()
assert plates_of(K(0.7)) == {Plate.K} and plates_of(CMYK(0.1, 0, 0, 0.9)) == {Plate.C, Plate.K}
```

`K(0.7)` is `0,0,0,0.7`; fractions are TeX's, so `K(70)` is refused (`TM-M017`). `plates_of(colour)` names the plates a
colour inks: a `CMYK` those with a component above zero, a `Gray` the K plate unless it is white, a `Spot` its own plate, a
`ColourPair` its print build, and an `RGB` all four (the output intent converts it). A colour value with no `plates` may
ink any process plate; a `plates` belongs to a colour (`TM-M069`). A tint or a mix keeps the plates only when both ends ink
the same ones ([Colour names](#colour-names)).

## Colour names

A field typed `ColourName` holds an xcolor name or expression. It is a `str`, built from a colour value so the name is not typed
by hand and the tint is a keyword, a fraction as everywhere in texmodel:

```python
from texmodel.interface import ColourName

assert ColourName("red") == "red" and ColourName("red", tint=0.5, mix="blue") == "red!50!blue"
```

`ColourName(Ink)` is `vl-ink`, `ColourName(Ink, tint=0.7)` is `vl-ink!70` and `ColourName(Ink, tint=0.7, mix=Paper)` is
`vl-ink!70!vl-paper`: 70% ink, 30% paper. `ColourName("red!50!blue")` takes an expression as written, `name`, `name!50` or `name!50!name`,
with numbers up to 100 (`TM-M067`); a tint outside 0 to 1 is `TM-M017`.

A node checks the colours its `ColourName` arguments use (`violations()`, and so `document` and `plan`): each must be a
colour value of its package or of its base, a colour one of its LaTeX libraries defines, or one of xcolor's base names
(`black blue brown cyan darkgray gray green lightgray lime magenta olive orange pink purple red teal violet white yellow`).
Anything else is `TM-C022` at the field, and an expression that is not that grammar is `TM-C023`. The names of the
`dvipsnames` or `svgnames` options are not known: declare the colour, or take a `Raw`. A node outside a package is not
checked, and neither are the colour keys of a `KeyVals`.

Both ends of a mix may ink the same plates and no others, so K-only ink is not mixed with a CMYK colour, a duotone or a
spot. `ColourName(TextInk, tint=0.7, mix=Paper)` is fine when `Paper` declares `plates = {Plate.K}`; with a colour that
inks other plates it is `TM-M068`, and the same expression written as a string is `TM-C024` when a node is checked, whoever
wrote it. `white` inks nothing and mixes with anything, and a plain tint `a!70` is a mix with white. In the `cmyk` model
xcolor's `black` and grays are the K plate and its other base names are process colours; a colour a library defines counts
as a process colour.

## Colours for print and screen

A brand that prints and shows on screen states each colour twice. `texmodel.ext.colourspace` holds both in a `ColourPair`
and declares the colour under one xcolor name, the CMYK definition when the print build is in use and the HTML one when
not. It is not a conversion between models: both builds are stated.

```python
from texmodel.ext.colourspace import ColourPair, ColourSpace, Dual, colour_of
from texmodel.ext.plates import K
from texmodel.interface import ColourName
from texmodel.package import Package

print_pkg = Package("acme-print-colours", prefix="pc")
ColourSpace().declare(print_pkg)                  # first: the cmyk and rgb options, and the flag


@print_pkg.value
class Ink(Value[Dual]):
    """Text ink."""

    default = ColourPair(cmyk=K(0.95), rgb="2d2c2b")


assert colour_of(Ink) == "pc-ink" and ColourName(Ink, tint=0.7) == "pc-ink!70"
assert r"\definecolor{pc-ink}{HTML}{2D2C2B}" in print_pkg.render()
```

A body or a field uses the name as any xcolor name: `\textcolor{pc-ink}{...}`, `fill=pc-ink!70`. A document picks the build
with a class option, `Document(options=["rgb"])`, which LaTeX gives to every package that declares it; CMYK is the default
(`ColourSpace(Build.RGB)` changes it). `colour_of(Ink)` is the name of any colour value (`Value[Colour]`, `Dual`,
`SpotColour`); a tint of it is xcolor's, in whichever build is in use.

- `rgb` is six hex digits, or an `RGB` rounded to 8 bits. Either side may be `None` (`TM-M064` if both are): a colour with
  no print build is undefined in print, which is xcolor's error and not a silent conversion.
- `ColourSpace` processes the package's options (`\ProcessOptions`, once per package), so it is declared before the colours
  and before any other options the package declares (`TM-M065`).
- A value that is not a registered colour is `TM-M066` in `colour_of`.

## Values only the whole document knows

The widest label and the number of cards are known only after the last card. `texmodel.ext.recorded` carries such a value
from one run to the next through the `.aux` (`latexmk` reruns until it stops moving). A `Recorded` has a `name`, a `kind`
(`Length`, `int` or `LENGTHS`, a list of lengths) and a `fold` that joins each measurement into it: `MAX`, `MIN`, `SUM`
or, for a list, `APPEND`.

```python
from texmodel.ext.recorded import MAX, SUM, Recorded

record, width = Recorded("LabelWidth").declare(pkg)               # \vlRecordLabelWidth{<length>}, the length \vlLabelWidth
count_record, count = Recorded("Cards", kind=int, fold=SUM).declare(pkg)
assert r"\newcommand{\vlRecordLabelWidth}[1]{%" in pkg.render()
assert MAX.reduce([12, 30, 20]) == 30 and SUM.reduce([1, 1, 1]) == 3
```

A card calls `\vlRecordLabelWidth{<its width>}` and reads `\vlLabelWidth`. A `MAX` or `MIN` value holds the fold of the last
run's value and this run's; a `SUM` holds the last run's alone, because a running total is partial. When a run ends with a
value other than the one it started from, it warns that the value is not settled, so a hand-driven single pass says so.

- The record is `\global`, because the `.aux` is read inside a group; a line the installed package does not know is
  swallowed, because the `.aux` may come from another version.
- Measure where a card names itself, at a fixed size, and not inside a box LaTeX defers: a measurement that depends on the
  value never settles.
- A `Fold` is data (`update`, `identity`, `idempotent`, and `reduce`, the same fold in Python as a test oracle); a `Fold` that
  does not take the kind is `TM-M058`. A name is capital-first letters (`TM-M056`), the kind `Length` or `int` (`TM-M057`),
  and the package needs a prefix (`TM-M059`).
- An `int` value is a macro that expands to the number (`\vlCards`, with no `\the`); a length is a register; a list is a
  macro that expands to the comma list. A `SUM` or an `APPEND` value is the last run's alone, as a running total or a list is
  partial. A list is compared as strings, because the `.aux` is read back with other catcodes.

## Text fitted to a band

`texmodel.ext.fit` sets a short line, such as a card title, to fit a band at sizes shared across the document. Each title
is fitted to the measure and to the band's height, and every title that can reach the `target` takes one main size, so a
deck reads as one design. A few shared smaller sizes serve only the titles that cannot reach it, and no size is below the
`floor`. Every title sits on one baseline, below the document's tallest ascent. The widths are measured in one run and used
in the next (`Recorded` carries them), so the first pass fits each title to itself and says the sizes are not settled.

```python
from texmodel.ext.fit import Fit, choose_sizes

fit = Fit("Title", target=Length("8mm"), floor=Length("3mm"), room=Length("12mm"), reduced_sizes=2)
parts = fit.declare(pkg)            # \vlRecordTitle{text}, \vlFitTitle{name}{text}, and the lengths below
assert r"\newcommand{\vlFitTitle}[2]{%" in pkg.render()
assert choose_sizes([30.0, 24.0, 12.0], 24.0, target=25.0, floor=8.0, reduced_sizes=2) == (24.0, 30.0)
```

A card calls `\vlRecordTitle{text}` where it names itself, and `\vlFitTitle{name}{text}` where the title is drawn; the
`name` is only for the log. Measure outside any box LaTeX defers: a single-face build neuters those boxes. `treatment` is the
one way a title is set (`Raw(r"\textbf{#1}")`), used to measure and to draw, so a title is never fitted to ink it is not set in.

- `Target`, `Floor` and `Room` are lengths a document may set; `Size` and `LineSize` hold the size the last title was set at
  and the main size the baseline belongs to.
- `reduced_sizes` is 0, 1 or 2 (`TM-M061`): zero is one size for everything; with two, the split of the titles that cannot
  reach the target puts the first `j` (largest first) in the upper group, the `j` that maximises `j * (o_j - o_n)`. The rule is
  `choose_sizes`, the oracle the TeX is tested against.
- A title too wide for the measure at the floor is named in a warning, and overflows: there is no wrapping.
- A name is capital-first letters (`TM-M060`), a size is positive and the floor is not above the target (`TM-M062`), and the
  package needs a prefix (`TM-M063`).

## PDF strings

A `PdfString` field holds text for the inside of a PDF literal string you write yourself
(`\pdfextension info{/Subject (#text)}`). It is written as `\detokenize{...}` with `( ) \` and every TeX special as an
octal escape (`\050`), and text with a non-ASCII character as UTF-16BE. A parenthesis cannot cut the string short, `%` or
`_` cannot break the TeX, and a reader gets the text back.

It is not for `\hypersetup{pdftitle=...}`: hyperref escapes its own input. For the PDF Info dictionary use `PdfInfo`
([Documents](documents.md#the-preamble)), which needs no escaping from you.
