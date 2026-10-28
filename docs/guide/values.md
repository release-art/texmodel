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

## Colours on one plate

`texmodel.ext.kplate` is for colours that ink the black plate only, such as text ink. `K(0.7)` is `0,0,0,0.7`; fractions
are TeX's, so `K(70)` is refused (`TM-M017`). `Value[KOnly]` holds only a `K`, in its default and in every setting, in
Python and in data (the schema says `number`, 0 to 1). `tint(Ink, 0.7)` is xcolor's `ac-ink!70`, which stays on the plate
because the base has only one: a tint of any other value is refused (`TM-M047`). `plates(colour)` names the plates a
colour inks and `is_single_plate(colour)` asks whether it is one or none.

```python
from texmodel.ext.kplate import K, KOnly, is_single_plate, tint
from texmodel.types import CMYK


@pkg.value
class TextInk(Value[KOnly]):
    """Text ink."""

    default = K(0.95)


assert r"\definecolor{vl-text-ink}{cmyk}{0,0,0,0.95}" in pkg.render()
assert tint(TextInk, 0.7) == "vl-text-ink!70"
assert is_single_plate(K(0.7)) and not is_single_plate(CMYK(0.1, 0, 0, 0.9))
```

## Values only the whole document knows

The widest label and the number of cards are known only after the last card. `texmodel.ext.recorded` carries such a value
from one run to the next through the `.aux` (`latexmk` reruns until it stops moving). A `Recorded` has a `name`, a `kind`
(`Length`, `int` or `LENGTHS`, a list of lengths) and a `fold` that joins each measurement into it: `MAX`, `MIN`, `SUM`
or, for a list, `APPEND`.

```python
from texmodel.ext.recorded import MAX, SUM, Recorded, reduce

record, width = Recorded("LabelWidth").declare(pkg)               # \vlRecordLabelWidth{<length>}, the length \vlLabelWidth
count_record, count = Recorded("Cards", kind=int, fold=SUM).declare(pkg)
assert r"\newcommand{\vlRecordLabelWidth}[1]{%" in pkg.render()
assert reduce(MAX, [12, 30, 20]) == 30 and reduce(SUM, [1, 1, 1]) == 3
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
