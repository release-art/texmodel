# Cookbook

Worked examples and the habits that keep a package easy to live with. Every `python` block here runs: `tests/test_docs.py`
executes them, so an example that stops working fails the build. The reference is the [README](../README.md); what is not
covered is in [known limitations](known-limitations.md).

## Settings

A `Value[T]` is a typed setting; the type of `T` decides the TeX.

```python
from texmodel.components import Value
from texmodel.package import Package
from texmodel.std.etoolbox import Toggle
from texmodel.types import RGB, Colour, Length, Text

pkg = Package("acme-cards", prefix="ac")


@pkg.value
class FactGap(Value[Length]):
    """Space under each fact."""

    default = Length("2mm")  # \newlength{\acFactGap} \setlength{\acFactGap}{2mm}


@pkg.value
class CardWidth(Value[Length]):
    """Set by the package once the page is known."""

    # no default: a bare \newlength, computed later by the package's own TeX


@pkg.value
class Ink(Value[Colour]):
    """Body text."""

    colour_name = "acInk"  # the xcolor name; without it the name is derived (`ac-ink`)
    default = RGB(0, 0, 0)


@pkg.value
class Draft(Value[Toggle]):
    """Print the draft banner."""

    default = False  # \newtoggle{acDraft} \togglefalse{acDraft}; the package then loads etoolbox


print(pkg.render())
```

- **Name colours the way the documents already do.** `colour_name` exists so a package can be migrated without renaming
  what every document references. Leave it out in a new package.
- **A length with no default** is for something the package computes at `\begin{document}`. Give a length a default
  whenever a sensible one exists: a documented default is a setting a document can rely on.
- **A toggle is for a switch the driver sets** (a build flag, a proof mode). A `Value[bool]` is a `\newif`; pick the one
  the surrounding TeX already tests.

## An optional argument with a default

An optional field is TeX's one optional argument. Its default is written in the definition too, so a hand-written
`\acRating{...}` gets the same default as a call from Python.

```python
from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw, Text

pkg = Package("acme-cards", prefix="ac")


@pkg.command
class Rating(Command):
    """A rating, shown with a mark."""

    text: Text
    mark: Raw | None = Raw(r"\acRatingMark")

    def body(self):
        return r"#mark\ #text"


print(pkg.render())  # \newcommand{\acRating}[2][\acRatingMark]{%
```

A `Text`, `Raw`, number, flag or `Choice` default reaches the definition; a key list, list or tuple has no single-argument
form and stays `[]`.

## Counting rules, enforced in TeX

A card's grammar (`children = [Fact.times(2, 3)]`) is checked in Python. Decks written by hand never pass through
Python, so the same rule can also be enforced when the document compiles. There is no flag for it. It is built from
ordinary parts, and the rule is written once, as a macro that takes the counter's name.

```python
from texmodel.body import Hole, Lit, Ref, Seq, Whitespace
from texmodel.components import Command, Environment
from texmodel.package import Package
from texmodel.std.etoolbox import IfNumGreater, IfNumLess
from texmodel.std.latex import CounterValue, NewCounter, PackageError, SetCounter, StepCounter
from texmodel.types import Raw, Text

pkg = Package("acme-cards", prefix="ac", whitespace=Whitespace.TRIM)
pkg.library("counters", NewCounter(Raw("acFacts")).render())  # \newcounter{acFacts}


def failure(word: str) -> Ref:
    """The error a rule raises; the region's name is the macro's third argument."""
    message = Seq(Lit(f"Too {word} "), Hole("what"), Lit(" on one card"))
    return PackageError.call(Raw("acme-cards"), message, Raw("See the card rules."))


@pkg.command
class CountAtMost(Command):
    """Count one more of a region and fail past its limit."""

    counter: Raw
    limit: Raw
    what: Raw

    def body(self):
        return [
            StepCounter.call(Hole("counter")),
            IfNumGreater.call(CounterValue.call(Hole("counter")), Hole("limit"), failure("many"), Raw("")),
        ]


@pkg.command
class CountAtLeast(Command):
    """Fail when a region has fewer than its minimum."""

    counter: Raw
    limit: Raw
    what: Raw

    def body(self):
        return [IfNumLess.call(CounterValue.call(Hole("counter")), Hole("limit"), failure("few"), Raw(""))]


@pkg.command
class Fact(Command, unused=("text",)):
    """A fact; a card allows two or three."""

    text: Text

    def body(self):
        return [CountAtMost.call(Raw("acFacts"), Raw("3"), Raw("facts")), r"#text"]


@pkg.environment
class Card(Environment):
    """A card."""

    children = [Fact.times(2, 3)]

    def begin(self):
        return [SetCounter.call(Raw("acFacts"), Raw("0"))]

    def end(self):
        return [CountAtLeast.call(Raw("acFacts"), Raw("2"), Raw("facts"))]


print(pkg.render())
```

The generated TeX counts as the document compiles: the maximum fails on the offending line, the minimum at
`\end{acCard}`, and the counter is reset by the environment's own `begin`, so no hooks are needed.

- **Write the rule once, give it the counter's name.** `CountAtMost` and `CountAtLeast` are reused for every region of
  every card. A package with many regions loops over its rules and calls them; it does not repeat the conditional.
- **Declare the counter** (`\newcounter`) where the package keeps its other low-level TeX, with `NewCounter` in a
  `library` block. Name it with the package's prefix so it cannot collide.
- **Use `Whitespace.TRIM`** on a package whose bodies are lists of calls: it ends each line with `%`, so no stray space
  reaches the typeset text.
- **Put the rule's source in the message.** The person who sees the error has a hand-written deck, not your Python.
- **This checks counts, not order.** Python's `validate()` also checks the order of children. If order matters in the
  deck, say so in the error text.
- **Do not nest the environment in itself.** The counters are global.

A call can be an argument of another call (`IfNumGreater.call(..., failure("many"), ...)`) wherever the argument is
`Raw`: a conditional's branch is TeX. A `Seq` holds several calls for one branch. A `Text` argument is text and takes no
call.

## Describing a component for tools

`doc` and `meta` on a field, and `meta` on a class, are carried into the JSON Schema, so a reference or a deck editor can
be generated from the same declaration instead of a parallel table.

```python
from texmodel.components import Command, field
from texmodel.package import Package
from texmodel.spec import json_schema
from texmodel.types import Text

pkg = Package("acme-cards", prefix="ac")


@pkg.command
class Picture(Command, unused=("source",)):
    """A picture."""

    meta = {"audience": "deck"}  # "x-audience": "deck" on the component
    source: Text = field(doc="The image file.", meta={"type": "file"})  # description, "x-type": "file"

    def body(self):
        return r"\includegraphics{#source}"


schema = json_schema(pkg)
assert schema["$defs"]["Picture"]["x-audience"] == "deck"
assert schema["$defs"]["Picture"]["properties"]["source"]["x-type"] == "file"
```

Keep the keys few and stable: they become part of what other tools read.

## A new kind of value, from a package you adopt

A `Value`'s kind is data (`ValueKind`): the type it holds, the names it takes, the TeX that declares and sets it, and the
packages it needs. `Toggle` in `texmodel.std.etoolbox` is the example to copy: it writes its TeX through the package's own
bindings (`NewToggle`, `ToggleTrue`), names the package it needs (`needs=(package,)`), and is used as `Value[Toggle]`.

- **Build a kind from the bindings you already declared**, not from strings: the binding is then the one place that knows
  the TeX, and a change to it reaches the kind.
- **Name the package as a `Package`, not a string,** when it is yours or one you adopt: the dependency is then checked
  with the rest (cycles, order).
- **Add a kind only when a value needs its own declaration.** A call (`Command`) is enough to *use* something; a kind
  is for a setting the package declares and a document sets.
