# Getting started

A card deck, from declaration to a checked `.sty`. The Python blocks on this page run in order, as one module.

## 1. Declare a package

A `Package` has a name and a prefix. Every public control sequence it defines starts with the prefix (`\acFact`).

```python
from texmodel.components import Command, Environment, Value
from texmodel.package import Package
from texmodel.types import CMYK, Colour, Length, Text

pkg = Package("acme-cards", prefix="ac", version="1.4.0", date="2026/10/21")


@pkg.value
class FactGap(Value[Length]):
    """Space under each fact."""

    default = Length("2mm")


@pkg.value
class Ink(Value[Colour]):
    """The text colour."""

    default = CMYK(0, 0, 0, 0.95)


@pkg.command
class Name(Command):
    """The subject's name, set as the title."""

    text: Text
    body = r"\par\noindent\textbf{\color{ac-ink}#text}\par"


@pkg.command
class Fact(Command):
    """One short sentence under the title."""

    text: Text
    body = r"\par\noindent{\color{ac-ink}#text}\par\vspace{\acFactGap}"


@pkg.environment
class CardBack(Environment):
    """The back face of a card."""

    children = [Name, Fact.times(2, 3)]
    begin = r"\begin{minipage}{\linewidth}"
    end = r"\end{minipage}"
```

- A field is an argument. `#text` in a body is the argument named `text`.
- A `Value[T]` needs no body: its type decides the declaration. `Length` is `\newlength` and `\setlength`, `Colour` is
  `\definecolor`, `bool` is `\newif`.
- `children` is the grammar of an environment: `Fact.times(2, 3)` is two to three facts.
- The docstring is required. It becomes the comment above the definition.

## 2. Render the package

```python
sty = pkg.render()
assert r"\newcommand{\acFact}[1]{%" in sty
```

```latex
% acme-cards.sty -- generated with texmodel 0.4.0. Do not edit; run `texmodel build`.
\NeedsTeXFormat{LaTeX2e}
\ProvidesPackage{acme-cards}[2026/10/21 v1.4.0 acme-cards]

\RequirePackage{xcolor}

% Space under each fact.
% from acme_cards.FactGap (value: Length)
\newlength{\acFactGap}
\setlength{\acFactGap}{2mm}

% One short sentence under the title.
% from acme_cards.Fact (body: inline)
\newcommand{\acFact}[1]{%
\par\noindent{\color{ac-ink}#1}\par\vspace{\acFactGap}
}
```

`xcolor` is required because a colour value needs it. The generator version in the header lets `check` say which
version wrote a file.

## 3. Write a document

A document is Python objects. `Text` fields are escaped; everything wrong is reported at once.

```python
card = CardBack(Name("Rex"), Fact("Friendly & loyal."), Fact("50% of $5"))
tex = pkg.document(card, settings=[FactGap(Length("3mm"))], options=["a4paper"])
assert r"\acFact{50\% of \$5}" in tex
```

```latex
\documentclass[a4paper]{article}
\usepackage{acme-cards}
\setlength{\acFactGap}{3mm}
\begin{document}
\begin{acCardBack}
\acName{Rex}
\acFact{Friendly \& loyal.}
\acFact{50\% of \$5}
\end{acCardBack}
\end{document}
```

A tree that breaks the grammar is reported with a code and a path:

```python
problems = CardBack(Fact("x")).violations()
assert [p.code for p in problems] == ["TM-C002", "TM-C002"]   # no Name; one Fact where 2 to 3 are allowed
```

## 4. Build and check from the command line

Point texmodel at the package in `pyproject.toml`:

```toml
[tool.texmodel]
package = "acme_cards:pkg"
output = "generated"
```

```zsh
texmodel build     # writes generated/acme-cards.sty
texmodel check     # exit 1 if a committed generated file is stale, missing or orphaned
```

Commit `generated/`. `texmodel check` in CI fails when someone edits the model and forgets to rebuild, or edits the
`.sty` by hand. A stale line names the component that differs: `changed generated/acme-cards.sty Fact: ...`.

## Next

- [Components](guide/components.md): bodies, calling other components, shared bases.
- [Arguments](guide/arguments.md): optional arguments, other delimiters, key lists.
- [TeX you already have](guide/adopting.md): start from a `.sty` you wrote by hand.
