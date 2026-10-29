# texmodel

[![CI](https://github.com/release-art/texmodel/actions/workflows/ci.yml/badge.svg)](https://github.com/release-art/texmodel/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Declare a LaTeX document family once, in Python types. texmodel renders it to plain, readable, git-trackable `.sty` source:
commit it, diff it, compile it with whatever LaTeX setup you already have. The same declarations give you documents as
Python objects, a JSON Schema for their data, checks that committed files are current, and typed compile diagnostics.

> **Status: alpha.** The public API may change before 1.0. What is missing today:
> [known limitations](docs/known-limitations.md).

```zsh
pip install texmodel                 # the library and the texmodel command
pip install 'texmodel[proof-pdf]'    # plus the proof-pdf verifier
```

```python
from texmodel.components import Command, Value
from texmodel.package import Package
from texmodel.types import Length, Text

pkg = Package("acme-cards", prefix="ac", version="1.4.0", date="2026/10/21")


@pkg.value
class FactGap(Value[Length]):
    """Space under each fact."""

    default = Length("2mm")


@pkg.command
class Fact(Command):
    """One short sentence under the title."""

    text: Text
    body = r"\par\noindent #text\par\vspace{\acFactGap}"


print(pkg.render())                       # the .sty
print(pkg.document(Fact(text="50% of $5")))    # \acFact{50\% of \$5}, escaped
```

```zsh
texmodel build     # writes generated/acme-cards.sty
texmodel check     # exit 1 if a committed generated file is stale, missing or orphaned
```

- **Deterministic.** No timestamps or hashes; the header records the generator version.
- **Checked early.** A bad declaration is refused when the class is defined, with a stable code (`TM-M0xx`) and the class
  named. A bad document reports everything wrong at once, each with a path.
- **Typed.** `Text` is escaped, `Raw` passes through; `Length`, colours, flags, choices and key lists are values, not strings.
- **No TeX needed to run.** The library never starts a process. `texmodel.run` is the optional `latexmk` driver.

## Documentation

| | |
|---|---|
| [Getting started](docs/getting-started.md) | declare, render, check: a worked first package |
| [Guide](docs/guide/components.md) | components, arguments, values, documents, adopting existing TeX, testing |
| [Cookbook](docs/cookbook.md) | worked examples |
| [Known limitations](docs/known-limitations.md) | what it does not do |
| [Plan and decisions](docs/texmodel-plan.md) | the target specification and the decisions log |

`pdm run mkdocs serve` builds the same pages as a site.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). Public API is the top-level modules of each package; everything under `_internal` may
change. Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## Licence

[MIT](LICENSE). The reference images carry their own licences (Ghostscript is AGPL); `texmodel run` runs them as a
separate process and ships none of their code.
