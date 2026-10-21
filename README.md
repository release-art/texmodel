# texmodel

[![CI](https://github.com/release-art/texmodel/actions/workflows/ci.yml/badge.svg)](https://github.com/release-art/texmodel/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A typed, declarative, verifiable model layer for LaTeX, in the spirit of an ORM: define the interface of a document
family once in Python types, write macro bodies as real TeX, and derive the rest (the `.sty`, JSON Schema, reference docs,
tests, migrations, a strict document API, structured compile results) from that one declaration.

> **Status: pre-alpha, not on PyPI.** Only the compile engine (stage A1 of the [plan](docs/texmodel-plan.md)) exists. The
> model layer (components, types, `.sty` generation, schema) is designed but not started.

## What works today

`texmodel` compiles a `.tex` file you wrote with `latexmk` and LuaLaTeX, and reports what happened as data instead of
log text.

- **Runs in the reference container** (`releaseart/lualatex-python:latest`, built from
  [proofpress](https://github.com/release-art/proofpress)) with no network, a read-only root filesystem, dropped
  capabilities, and memory, CPU, process and time limits. `--local` runs on your machine instead.
- **Typed diagnostics** with stable codes, parsed from the log: undefined control sequences (`TM-X010`), missing glyphs
  (`TM-X011`, an error by default), overfull boxes (`TM-X012`), missing files (`TM-X013`), package errors (`TM-X014`),
  undefined references (`TM-X018`), and a fallback for any other TeX error (`TM-X020`). A failed compile whose log explains
  nothing is reported as `TM-X099`, never as silence.
- **Convergence**: when the document never settles within `--passes`, the `.aux` entries that keep changing are named
  (`TM-X030`).
- **Reproducible mode** (`--epoch N` pins `SOURCE_DATE_EPOCH`): two builds give byte-identical PDFs.
- **A content-addressed cache** keyed on sources, asset roots, image id and settings. A new image is a miss.
- **Ordered asset roots** (`--root`, earlier wins) with a report of what a root shadows.
- **Build targets** declared in `pyproject.toml`, built in parallel.

```zsh
pdm install                                   # Python 3.15; Docker for the container (or --local with latexmk installed)

texmodel doctor                               # what this machine and the configured image can do
texmodel compile doc.tex                      # exit 0 ok, 1 errors in the document, 3 tool or image missing
texmodel compile doc.tex --json --epoch 1700000000
texmodel build -j 4                           # every [tool.texmodel.targets.*]
texmodel clean doc.tex --all
```

Configuration lives in `pyproject.toml`; there is no second manifest.

```toml
[tool.texmodel]
prefix = "ac"
image = "releaseart/lualatex-python:latest"   # omit to run on the host

[tool.texmodel.targets.card]
source = "card.tex"
```

From Python:

```python
import pathlib
from texmodel import Compiler

result = Compiler(image="releaseart/lualatex-python:latest", epoch=1700000000).compile(
    pathlib.Path("doc.tex"), pathlib.Path(".texmodel/build/doc")
)
for d in result.diagnostics:
    print(d.severity, d.code, d.file, d.line, d.message)
result.raise_for_status()   # CompileError carrying every diagnostic
```

A failed compile is a result, not an exception: check `result.ok`, or call `raise_for_status()`.

### Notes

- The image is `latest` on purpose; every result records the image tag, id and revision, so builds stay traceable.
- The image must contain `latexmk`. Until [proofpress](https://github.com/release-art/proofpress) releases one that does,
  the container compile tests need a derived image (`FROM releaseart/lualatex-python` plus `tlmgr install latexmk`), and the
  `tex` CI job is allowed to fail.
- Reads are restricted, not paranoid, because paranoid reads break luaotfload; the container's read-only mounts are the
  boundary. Whether a hostile `\directlua` can read outside them is an open item (plan Z2).

## Where it is going

The plan has three stages with go/no-go gates. See [docs/texmodel-plan.md](docs/texmodel-plan.md) for the requirements and
[docs/texmodel-research-notes.md](docs/texmodel-research-notes.md) for the reasoning behind them.

| Stage | Contents | State |
|---|---|---|
| A0 | repo, standards, errors, config, CLI shell, `doctor` | done |
| A1 | the compile engine described above | built; Gate A waits for an image with `latexmk` |
| A2 | verifier plugins, drift `check`, `bundle`/`install` | next |
| B | types, components, bodies, `.sty` generation, `Doc` trees, schema | after Gate A |
| C | migrations, adoption of hand-written TeX, a standard library, print extra, docs, 1.0 | after Gate B |

## Public API

The top-level modules of `texmodel` are public: `compiler`, `config`, `diagnostics`, `engines`, `errors`, `result`, `roots`,
`targets` and `cli`. Everything under `texmodel._internal` may change at any time.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: `bin/autoformat.sh` (ruff, pyright strict, import-linter) and `bin/test.sh`
(pytest, 100% coverage gate). The container compile suite is `pytest -m tex`; it skips without an image that has `latexmk`,
and `TEXMODEL_REQUIRE_TEX=1` turns that skip into a failure. `TEXMODEL_TEST_IMAGE` overrides the image.

Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## Licence

[MIT](LICENSE). The reference images carry their own licences (Ghostscript is AGPL); texmodel runs them as a separate
process and ships none of their code.
