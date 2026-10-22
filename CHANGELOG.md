# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Rendering core (plan B): `texmodel.components` (`Command`, `Environment`, `Value[T]`, `TemplateRef`), `texmodel.package.Package`
  and `texmodel.types`. A component is a class; its fields are its arguments (an optional field is keyword-only and TeX's
  one optional argument) and its docstring is its documentation. `Package.render()` writes a deterministic `.sty` with a
  provenance comment per component. Declarations are refused at class definition with stable `TM-M0xx` codes.
  `texmodel build` and `texmodel check` (`[tool.texmodel] package`, `output`) write and drift-check the generated files.
- Bodies are explicit TeX: a `body` method returning it (or a string attribute), or a `TemplateRef("file.tex")`, resolved
  relative to the module that defines the class. `Environment` has `begin` / `end` in the same way. A method is read once,
  when the class is defined, and cannot use `self`; indentation and surrounding blank lines are removed.
- `Value[Length | Colour | Bool]` renders `\newlength` + `\setlength`, `\definecolor` (`ac-ink`, `ac-brand-red`) or `\newif`.
  `texmodel.types` has `Length`, `CMYK`, `RGB`, `Gray`, `Colour`, `Bool`, `Raw` and `escape`. `needs_packages` is data on the
  component; the `.sty` emits the sorted union as `\RequirePackage` lines (M14). A body naming an undeclared
  `\<prefix>Name` is refused at `render()` / `texmodel check` (`TM-M015`).
- Documents (T3, M4, D1, D1a, D2, E2): `Package.document(*nodes, settings=, options=)` renders a complete `.tex`. `Command` and
  `Environment` instances `render()` and `validate()`. `Text` fields are escaped; `Raw` is a distinct, brace-balanced type
  for TeX that must pass through. An environment's `children = [Name, Fact.times(2, 3), ...]` grammar is checked by
  `validate()`, which returns every `Violation` with a path (`TM-C001`-`C003`, `C006`, `C007`); rendering raises them as an
  `ExceptionGroup`. `repr()` of a node is the constructor expression.
- `texmodel render module:attr [-o out.tex]` writes a document (a `str` from `Package.document()`, or a function returning
  one). An invalid document prints every violation with its code and path and exits 2.
- `tests/examples/`: complete example packages with committed output, compared by the test suite and compiled by the
  `tex` suite.
- `texmodel-build`: a second package in this repo (`harness/`) holding the compile and verify side; `texmodel` itself never
  spawns a process. Its configuration is `[tool.texmodel-build]`.
- `texmodel_build.Compiler`: a thin `latexmk` driver (host, or `docker run` over an image) returning a typed
  `CompileResult` with parsed diagnostics (`TM-X0xx`), page and pass counts, probes and tool versions; ordered asset
  roots, font directories, `--epoch`, convergence diagnostics, `clean`. `texmodel-build` has `compile`, `build` (targets
  from `[tool.texmodel-build.targets]`), `clean`, `verify` and `doctor`.
- Verifier plugins (`texmodel_build.verifiers` entry points) with the rule that anything unconfirmable fails; an optional
  adapter over proof-pdf (`texmodel-build[proof-pdf]`).
- `texmodel.drift` and `texmodel.bundle`: byte-for-byte drift detection (stale, missing, orphaned) and a manifest copy that
  refuses if any source is missing.
