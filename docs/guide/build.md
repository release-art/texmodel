# Building and compiling

`texmodel run` is optional. It is a thin `latexmk` driver that turns a compile into data: typed diagnostics with stable
codes, a result you can test. Your own `latexmk` or image works just as well.

```zsh
texmodel run doctor                       # tools on this machine, and what the configured image has
texmodel run doctor --sty 'res/*.sty'     # which files those packages load that the toolchain lacks (kpsewhich), with a tlmgr line; exit 3
texmodel run compile doc.tex              # exit 0 ok, 1 errors in the document, 3 tool or image missing
texmodel run compile doc.tex --json --epoch 1700000000 --root generated
texmodel run compile deck.tex --plan "deck.build:plan()"   # diagnostics name the component: [Card[1]/CardBack[1]/Name[0]]
texmodel run build -j 4                   # every [tool.texmodel.run.targets.*]
texmodel run verify out/*.pdf             # verifier plugins; anything unconfirmable fails
texmodel run clean doc.tex                # remove its build output; --all also removes the PDF
```

```toml
[tool.texmodel.run]
image = "releaseart/lualatex-python:latest"   # runs `docker run` over it; omit to run on this machine
```

The image must contain `latexmk`. `doctor` reports it if not.

## From Python

`texmodel.run` is async: what starts a process is awaited, so a compile does not block an event loop.

```py
from texmodel.run import Compiler
from texmodel.run.targets import build_targets

result = await Compiler(image="releaseart/lualatex-python:latest").compile(src, out, plan=plan)
summary = await build_targets(targets, compiler, root=root, outdir=out, jobs=4)  # up to 4 compiles at once
```

A compile past its `timeout`, or cancelled (`task.cancel()`, a `TaskGroup` that fails), kills its process group
(`latexmk` and the engine it started), and in the image its container, before it returns or re-raises. From synchronous code, `asyncio.run(...)`.

## Diagnostics

The compile log becomes typed diagnostics with stable codes:

| Code | Meaning |
|---|---|
| `TM-X010` | undefined control sequence |
| `TM-X011` | missing glyph |
| `TM-X012` | overfull box |
| `TM-X013` | missing file |
| `TM-X014` | package error |
| `TM-X018` | undefined reference |
| `TM-X019` | package warning, with its continuation lines |
| `TM-X030` | non-convergence, with the `.aux` entries that keep moving |

A fallback means no failure is silent. A package warning is how a hand-written package says a card does not fit
(`TM-X019`).

Each diagnostic has its file and line. A warning's `on input line N` names no file, so every compile marks in the log each
TeX file it opens and closes (a LuaTeX callback run before the document; the PDF is unchanged), and the line is placed in
the file open at that point: a warning raised in an `\input` part or in a package while it loads names that file, not the
main document. A line the log places in no file has no file and is not mapped to a component.

## Does not fit

A package's "does not fit" warning becomes a typed `Overset` (`TM-X031`, an error: item, needs, has, over, in pt) when a rule
says how to read it. The warning is kept too. A package that prints `texmodel:probe:fit.<item>=<needs>/<has>` needs no rule.
Lengths take `pt`, `mm`, `cm`, `in` (a bare number is pt); an item that fits gives none.

```toml
[tool.texmodel.run.measures.card-fit]
package = "card-deck"
pattern = "Card '(?P<item>[^']+)' does not fit. Its body needs (?P<needs>\\S+) and the card has (?P<has>\\S+)"
```

## Verifying PDFs

`texmodel run verify` runs plugins from the `texmodel.run.verifiers` entry-point group. `pip install 'texmodel[proof-pdf]'`
adds [proof-pdf](https://github.com/release-art/proofpress). A verifier that cannot run, a file that cannot be opened and a
profile that selects nothing are failures; the only excuse is a declared `exempt` glob.

## Embedded fonts

luaotfload replaces a font it cannot find with a system one, without an error. `texmodel.run.fonts.embedded(log, cwd)`
lists the font files the LuaTeX log says were embedded (relative ones against the source's directory), and
`outside(log, allowed, cwd)` the ones not under the `allowed` directories: empty means the document is self-contained.
A font inside an included PDF is not in the log.

## Reproducibility

Reproducibility is the image's job. `--epoch` pins `SOURCE_DATE_EPOCH`. There is no sandbox or cache here.

A generated file's header records the texmodel version. A copy of texmodel embedded in a wheel has no installed metadata to
read it from; set `texmodel.package.GENERATOR_VERSION` in the copy.
