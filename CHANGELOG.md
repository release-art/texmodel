# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Macro interfaces (`texmodel.interface`): `arg()` states how a field is written (delimiters
  `{}` `[]` `()` `<>`, several optional arguments with `fill=`, `Star` and other tokens, `SlotGroup`), and fields may be
  `Length` (`Length.expr` for a TeX expression), `Colour`, `ColourName`, `int`, `float`, `bool`, tuples and records, lists and
  key lists. A signature `\newcommand` cannot define is defined with `\NewDocumentCommand`; stubs and the interface check
  read it.
- `texmodel.std.calc`: the whole `calc` package as a typed expression language. `IntExpr`, `DimenExpr` and `GlueExpr` with
  `+ - * /`, `real`, `ratio`, `widthof` and the other text sizes, `maxof`, `minof`, and the commands it extends or adds.
  Mistakes TeX would refuse (`2cm+4`) are a `TypeError`; the values are checked by compiling.
- Key lists: `KeyVals` (`texmodel.keyvals`) with `Flag`, `Switch`, `Item`, `OptionalValue`, nested and repeated keys, and
  `KeyRules` presets for pgfkeys, xkeyval, keyval, kvoptions and l3keys (`texmodel.keys`).

### Changed

- `texmodel.std`: `adjustbox`, `graphicx`, `geometry`, `tcolorbox` and `tikz` take typed key lists instead of `Raw`;
  `\vspace`, `\hspace`, `\setlength`, `\addtolength` and `minipage` take a `Length`; added `\makebox`, `\raisebox` and the
  sectioning commands.
- `TM-M003` (more than one optional argument) is removed; an optional argument followed by another that says nothing
  about being skipped is `TM-M037`.

## [0.2.0] - 2026-10-22

First release (0.1.0 was never published).

- `texmodel`: declare LaTeX components (`Command`, `Environment`, `Value[T]`) as typed Python classes and render a
  deterministic `.sty`, documents and a JSON schema; check committed output for drift; adopt hand-written TeX; a standard
  library of headers (`texmodel.std`).
- `texmodel_build` and the `texmodel-build` command: a `latexmk` driver with typed diagnostics, and verifier plugins
  (`texmodel[proof-pdf]`).

[Unreleased]: https://github.com/release-art/texmodel/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/release-art/texmodel/releases/tag/v0.2.0
