# texmodel

Declare a LaTeX document family once, in Python types. texmodel renders it to plain, readable `.sty` source that you commit,
diff and compile with whatever LaTeX setup you already use. The same declarations give you documents as trees of Python
objects, a JSON Schema for their data, checks that the committed files are current, and typed compile diagnostics.

!!! note "Alpha"
    The public API may change before 1.0. What is missing today is in [known limitations](known-limitations.md).

## What you get

- **Plain output.** A `.sty` with no timestamps or hashes. The same declarations always give the same bytes.
- **Early errors.** A bad declaration is refused when the class is defined, with a stable code (`TM-M0xx`) and the class named.
  A bad document reports everything wrong at once, each with a path such as `Card/CardBack[1]/Fact[2].text`.
- **Checked against TeX.** `texmodel check` fails when a committed file is stale. For hand-written TeX it compares what you
  declared with what the file defines.
- **No TeX needed to run.** The library never starts a process. `texmodel-build` is the optional `latexmk` driver.

## Install

```zsh
pip install texmodel                 # the library and the texmodel-build command
pip install 'texmodel[proof-pdf]'    # plus the proof-pdf verifier
```

Python 3.15 and LuaLaTeX only.

## Two packages

| Package | What it is |
|---|---|
| `texmodel` | The library: declare components, render TeX, check committed output. |
| `texmodel_build` | Optional: a `latexmk` driver with typed log diagnostics, and verifier plugins for built PDFs. |

## Where to go

| If you want to... | Read |
|---|---|
| see it work in ten minutes | [Getting started](getting-started.md) |
| declare commands, environments and values | [Guide](guide/components.md) |
| keep a `.sty` you wrote by hand | [TeX you already have](guide/adopting.md) |
| copy a worked example | [Cookbook](cookbook.md) |
| know what it does not do | [Known limitations](known-limitations.md) |
