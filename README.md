# texmodel

[![CI](https://github.com/release-art/texmodel/actions/workflows/ci.yml/badge.svg)](https://github.com/release-art/texmodel/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Declare a LaTeX document family once in Python types; get plain, readable, git-trackable `.sty` source out of it. The output
is ordinary TeX: commit it, diff it, compile it with whatever LaTeX setup you already have.

> **Status: pre-alpha, not on PyPI.** One component kind (`Command`) renders to a `.sty` today. Environments, values,
> `Doc` trees, schema export and migrations are designed (see [the plan](docs/texmodel-plan.md)) but not built.

This repository holds two packages, released in lockstep:

| Package | What it is |
|---|---|
| **`texmodel`** (`src/`) | The library: declare components, render deterministic TeX, check that committed output is current. No TeX needed, no processes spawned. |
| **`texmodel-build`** (`harness/`) | Optional: a thin `latexmk` driver with typed log diagnostics, and verifier plugins for built PDFs. Use it if you want compile results as data; your own `latexmk` or image works just as well. |

## texmodel

```python
# acme_cards/__init__.py
from texmodel.components import Command, Environment, Value
from texmodel.package import Package
from texmodel.types import CMYK, Bool, Colour, Length, Text

pkg = Package("acme-cards", prefix="ac", version="1.4.0", date="2026/10/21")

@pkg.value
class FactGap(Value[Length]):
    """Space under each fact."""
    default = Length("2mm")

@pkg.value
class Ink(Value[Colour]):
    """The text colour."""
    default = CMYK(0, 0, 0, 0.95)

@pkg.value
class Compact(Value[Bool]):
    """Tighten the layout."""
    default = False

@pkg.command
class Fact(Command):
    """One short sentence under the title."""
    text: Text

@pkg.command
class Slot(Command):
    """A labelled paragraph; the label prints as its heading."""
    text: Text
    label: Text | None = None      # optional: keyword-only, TeX's one optional argument

@pkg.environment
class CardBack(Environment):
    """The back face of a card."""
    children = [Name, Fact * (2, 3), Slot * (0, 3)]   # order and counts; `* "?"`, `* "*"`, `* "+"` also work
```

The body is TeX in a file named after the class, beside it (`acme_cards/fact.tex`), or an inline `body="..."` for a line
or two. `#text` is the argument named `text`:

```latex
\par\noindent{\color{ac-ink}#text}\par\vspace{\acFactGap}
\ifacCompact\vspace{-\acFactGap}\fi
```

A `Value[T]` needs no body: its type decides the declaration (`Length` -> `\newlength` + `\setlength`, `Colour` ->
`\definecolor` named `ac-ink`, `Bool` -> `\newif`), and its `default` is an instance of `T`. Packages a value needs
(`xcolor` for colours) are `\RequirePackage`d once, sorted. A body that names an undeclared `\acThing` is refused when
`render()` / `texmodel check` runs (not at registration, since a body may name a component declared after it).

An environment's bodies are `card_back.begin.tex` and `card_back.end.tex` (or `begin=` / `end=`). A document is plain
Python; `Text` fields are escaped, a `Raw` field passes TeX through, and everything wrong is reported at once:

```python
tex = pkg.document(
    CardBack(Name("Rex"), Fact("Friendly & loyal."), Fact("50% of $5")),
    settings=[FactGap(Length("3mm"))],       # values for the whole document
    options=["a4paper"],
)
CardBack(Fact("x")).validate()   # [Violation(TM-C002 ...), Violation(TM-C001 path='CardBack/Fact[0]' ...)]
```

```toml
# pyproject.toml
[tool.texmodel]
prefix = "ac"
package = "acme_cards:pkg"
output = "generated"
```

```zsh
texmodel build     # writes generated/acme-cards.sty
texmodel render docs:card   # writes card.tex from `card = pkg.document(...)` (or a function returning one); -o to choose
texmodel check     # exit 1 if a committed generated file is stale, missing or orphaned
```

```latex
% generated/acme-cards.sty (excerpt)
\RequirePackage{xcolor}

% Space under each fact.
% from acme_cards.FactGap (value: Length)
\newlength{\acFactGap}
\setlength{\acFactGap}{2mm}

% The text colour.
% from acme_cards.Ink (value: Colour)
\definecolor{ac-ink}{cmyk}{0,0,0,0.95}
```

- **Deterministic**: no timestamps or hashes; the header records the generator version (`generated with texmodel X.Y.Z`),
  so `check` can say "written by 0.1.0, current is 0.2.0".
- **Checked early**: a bad declaration is refused when the class is defined, with a stable code (`TM-M0xx`) and the class
  named: more than one optional argument, a name that is not a TeX control word, a missing or ambiguous body, a `#name` that
  is not a field, an argument the body never uses, unbalanced braces, a name collision.
- **Typed**: `Fact("A soft woof.")` type-checks; fields are `Text`, `Raw` or either `| None`; values are `Length`, `CMYK`/`RGB`/`Gray` (components in [0, 1], no conversion between models) or `bool`.

`texmodel.bundle` copies a manifest of files and refuses if any is missing (`stale` compares bytes, not timestamps);
`texmodel.drift` is what `check` uses.

## texmodel-build

```zsh
texmodel-build doctor                       # tools on this machine, and what the configured image has
texmodel-build compile doc.tex              # exit 0 ok, 1 errors in the document, 3 tool or image missing
texmodel-build compile doc.tex --json --epoch 1700000000 --root generated
texmodel-build build -j 4                   # every [tool.texmodel-build.targets.*]
texmodel-build verify out/*.pdf             # verifier plugins; anything unconfirmable fails
```

```toml
[tool.texmodel-build]
image = "releaseart/lualatex-python:latest"   # runs `docker run` over it; omit to run on this machine
```

- The compile log becomes typed diagnostics with stable codes: undefined control sequences (`TM-X010`), missing glyphs
  (`TM-X011`), overfull boxes (`TM-X012`), missing files (`TM-X013`), package errors (`TM-X014`), undefined references
  (`TM-X018`), non-convergence with the `.aux` entries that keep moving (`TM-X030`), and a fallback so no failure is silent.
- Reproducibility is the image's job (`--epoch` pins `SOURCE_DATE_EPOCH`); there is no sandbox or cache here.
- `texmodel-build verify` runs plugins from the `texmodel_build.verifiers` entry-point group. `pip install
  'texmodel-build[proof-pdf]'` adds [proof-pdf](https://github.com/release-art/proofpress). A verifier that cannot run, a
  file that cannot be opened and a profile that selects nothing are failures; the only excuse is a declared `exempt` glob.
- The image must contain `latexmk` (`releaseart/lualatex-python` has it since proofpress v0.3.4); `doctor` reports it if not.

## Where it is going

| Step | Contents | State |
|---|---|---|
| A | build harness: compile, typed diagnostics, verifier plugins, drift, bundle | built |
| B | rendering core: types, `Command`/`Environment`/`Value`, `.sty`, `Doc` trees, schema | `Command` → `.sty` and `build`/`check` done |
| C | migrations, adopting hand-written TeX, a standard library, docs, 1.0 | after B |

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). `bin/autoformat.sh` runs ruff, strict pyright and import-linter over both packages;
`bin/test.sh` runs pytest with a 100% coverage gate. The container compile suite is `pytest -m tex`; it skips without an
image that has `latexmk`, and `TEXMODEL_REQUIRE_TEX=1` turns that skip into a failure (`TEXMODEL_TEST_IMAGE` sets the image).

Public API is the top-level modules of each package; everything under `_internal` may change. Report vulnerabilities as
described in [SECURITY.md](SECURITY.md).

## Licence

[MIT](LICENSE). The reference images carry their own licences (Ghostscript is AGPL); `texmodel-build` runs them as a
separate process and ships none of their code.
