# Building and compiling

`texmodel-build` is optional. It is a thin `latexmk` driver that turns a compile into data: typed diagnostics with stable
codes, a result you can test. Your own `latexmk` or image works just as well.

```zsh
texmodel-build doctor                       # tools on this machine, and what the configured image has
texmodel-build doctor --sty 'res/*.sty'     # which files those packages load that the toolchain lacks (kpsewhich), with a tlmgr line; exit 3
texmodel-build compile doc.tex              # exit 0 ok, 1 errors in the document, 3 tool or image missing
texmodel-build compile doc.tex --json --epoch 1700000000 --root generated
texmodel-build compile deck.tex --plan "deck.build:plan()"   # diagnostics name the component: [Card[1]/CardBack[1]/Name[0]]
texmodel-build build -j 4                   # every [tool.texmodel-build.targets.*]
texmodel-build verify out/*.pdf             # verifier plugins; anything unconfirmable fails
```

```toml
[tool.texmodel-build]
image = "releaseart/lualatex-python:latest"   # runs `docker run` over it; omit to run on this machine
```

The image must contain `latexmk`. `doctor` reports it if not.

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

## Does not fit

A package's "does not fit" warning becomes a typed `Overset` (`TM-X031`, an error: item, needs, has, over, in pt) when a rule
says how to read it. The warning is kept too. A package that prints `texmodel:probe:fit.<item>=<needs>/<has>` needs no rule.
Lengths take `pt`, `mm`, `cm`, `in` (a bare number is pt); an item that fits gives none.

```toml
[tool.texmodel-build.measures.card-fit]
package = "card-deck"
pattern = "Card '(?P<item>[^']+)' does not fit. Its body needs (?P<needs>\\S+) and the card has (?P<has>\\S+)"
```

## Verifying PDFs

`texmodel-build verify` runs plugins from the `texmodel_build.verifiers` entry-point group. `pip install 'texmodel[proof-pdf]'`
adds [proof-pdf](https://github.com/release-art/proofpress). A verifier that cannot run, a file that cannot be opened and a
profile that selects nothing are failures; the only excuse is a declared `exempt` glob.

## Embedded fonts

luaotfload replaces a font it cannot find with a system one, without an error. `texmodel_build.fonts.embedded(log, cwd)`
lists the font files the LuaTeX log says were embedded (relative ones against the source's directory), and
`outside(log, allowed, cwd)` the ones not under the `allowed` directories: empty means the document is self-contained.
A font inside an included PDF is not in the log.

## Reproducibility

Reproducibility is the image's job. `--epoch` pins `SOURCE_DATE_EPOCH`. There is no sandbox or cache here.
