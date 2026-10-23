# Values and settings

A `Value[T]` is a setting: a length, a colour, a flag, a text or a piece of TeX. Its type decides the declaration, so it
needs no body. The blocks on this page run in order, as one module.

```python
from texmodel.components import Value
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
tex = pkg.document(settings=settings)
assert r"\setlength{\vlGap}{3mm}" in tex
assert r"\renewcommand{\vlDeckName}{R\&D}" in tex
```

Every setting, of any type, is written right after `\usepackage`, in the order given, before the `after_package` entries
and `\begin{document}`. What the package computes in the preamble therefore already sees it. This order is tested.

`setting_line(value)` is the line written for one setting:

```python
assert setting_line(Gap(Length("3mm"))) == r"\setlength{\vlGap}{3mm}"
```

## PDF strings

A `PdfString` field holds text for the inside of a PDF literal string you write yourself
(`\pdfextension info{/Subject (#text)}`). It is written as `\detokenize{...}` with `( ) \` and every TeX special as an
octal escape (`\050`), and text with a non-ASCII character as UTF-16BE. A parenthesis cannot cut the string short, `%` or
`_` cannot break the TeX, and a reader gets the text back.

It is not for `\hypersetup{pdftitle=...}`: hyperref escapes its own input. For the PDF Info dictionary use `PdfInfo`
([Documents](documents.md#the-preamble)), which needs no escaping from you.
