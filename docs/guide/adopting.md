# TeX you already have

Two ways to start from TeX that exists: declare what a hand-written `.sty` defines, or carry blocks of TeX into a generated
`.sty`. The blocks on this page run in order, as one module.

## Adopt a hand-written package

`Package(..., adopted=True)` declares a package texmodel does not write. The components have no body, `build` writes no file,
documents are still checked and escaped, and `texmodel check` compares each declaration with the TeX it names.

```python
from texmodel.components import Command, Value
from texmodel.package import Package, declared
from texmodel.types import Text

pkg = Package("card-deck", prefix="cd", adopted=True)     # the package name is the hand-written one


@pkg.command
class TalkAboutMe(Command):
    """A question, with an optional answer."""

    question: Text
    answer: Text | None = None            # declared [2][]: \newcommand{\cdTalkAboutMe}[2][]{...}


@pkg.command
class DeckName(Command):
    """The deck name printed on every card; a setting the deck sets with \\renewcommand."""
```

```toml
[tool.texmodel]
package = "deck.model:pkg"
sources = ["res/brand/*.sty"]            # globs, relative to pyproject.toml
```

```zsh
texmodel check     # TM-C010: declared, not defined; TM-C011: defined with another signature
```

The check runs both ways: a public `<prefix>Name` the sources define that nothing declares is `TM-C025`. Declare it (a
length or a flag the package defines is a `Command` with no arguments), or name the helper outside the public namespace,
with an `@` in it.

The scan is regex-level and honest about it. It reads `\newcommand`, `\providecommand`, `\DeclareRobustCommand`,
`\newenvironment`, the xparse `\NewDocumentCommand` family, `\newlength`, `\newsavebox`, `\newfontfamily`, `\newtoggle`,
`\newif` (with `\Xtrue` and `\Xfalse`), `\definecolor`, `\colorlet` and `\newcounter`. A name defined any other way (`\def`,
`\let`, an expl3 definer) counts as missing. Reading TeX beyond that is not planned ([known limitations](../known-limitations.md)).

`declared(text)` is the set of control sequences those forms declare in a text, without the backslash. A colour or a counter
is not one.

```python
assert declared(r"\newcommand{\cdA}[1]{} \newif\ifcdB \def\cdC{}") == {"cdA", "ifcdB", "cdBtrue", "cdBfalse"}
```

A complete example (a hand-written package, the generator it replaces and a three-card deck) is in
`tests/consumers/card_deck/`.

## Library blocks

`pkg.library(name, source)` carries TeX into the generated `.sty` as it is: dedented, blank edges removed, no `%` added,
`#1` and `##1` as written, in registration order among the package's items, under a provenance comment. `source` is a string
or a `TemplateRef`. The only static checks are balanced braces (`TM-M011`) and, in an expl3 block, no `\ExplSyntaxOn` or
`\ExplSyntaxOff` inside (`TM-M034`). A name is used once (`TM-M007`).

A component with `defined_by` is declared and callable but renders no definition: the block defines it.

```python
from texmodel.body import Syntax
from texmodel.types import Raw

lib = Package("sizing-kit", prefix="cd")
sizing = lib.library(
    "sizing",
    r"""
    \fp_new:N \l__cd_size_fp
    \newcommand{\cdFitSize}[2]{ \fp_set:Nn \l__cd_size_fp { min ( 14 , max ( 8 , 12 * #2 / #1 ) ) } }
    """,
    syntax=Syntax.EXPL3,
)


@lib.command
class FitSize(Command):
    """Work out the title size."""

    defined_by = sizing
    natural: Raw
    available: Raw


assert lib.check_parts() == []
```

A component with `defined_by` has no body (`TM-M032`) and its block belongs to the same package (`TM-M033`).
A flag, toggle, length, colour or text setting that a block defines is a `Value` with `defined_by`: it has no default, `cs`
gives the whole control sequence and `colour_name` the colour's name.

### What `check` reports

`texmodel check` reads each block with `Package.check_parts()`, with no TeX needed:

| Code | Meaning |
|---|---|
| `TM-C010` | a declared component the block does not define |
| `TM-C011` | defined with another signature |
| `TM-C012` | a public `<prefix>Name` the block defines that nothing declares |
| `TM-C013` | a name defined twice (generation itself refuses it: `TM-P012`) |

An expl3 block is not read; whether TeX really defines a name, with that many arguments, is checked by compiling:
`await texmodel.run.testkit.check_library(compiler, pkg)` builds `pkg.test_document(...)` with `export_probes(pkg)`, compiles it, and
returns `TM-C010` for a name the block does not define and `TM-C011` for another number of arguments (`?` is checked for
existence only). The arity is the number of `#` in the macro's `\meaning`, so a command defined with `\NewDocumentCommand` or
with an optional first argument reports `0`. A block that TeX refuses fails the compile with the block's name as the
diagnostic's `path`.

## Parts filled from a model

A package that starts from TeX you already have can be a list of parts filled from a model:
`pkg.library(name, TemplateRef("brand.tex"), fill=model)`. `fill` is a mapping, a dataclass or a pydantic model, and the
text's `<<name>>` holes (`<<a.b>>` into a nested model) are filled by type: `str` is escaped, `Raw` passes through, and a
`Length`, a colour model, a number or a flag is written as it is.

```python
from dataclasses import dataclass

from texmodel.types import Length


@dataclass
class Brand:
    name: str
    gap: Length


parts = Package("parts-kit", prefix="pk")
parts.library("brand", r"\newcommand{\pkBrand}{<<name>>}\newlength{\pkGap}\setlength{\pkGap}{<<gap>>}", fill=Brand("R&D", Length("2mm")))
assert r"\newcommand{\pkBrand}{R\&D}" in parts.render()
```

A hole the model has no field for is `TM-M041`, a value of another type `TM-M040`; a model may hold more than the part uses.
Without `fill` a block is carried exactly as it is. [The cookbook](../cookbook.md) has a worked example.
