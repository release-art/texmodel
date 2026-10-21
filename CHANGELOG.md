# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Rendering core (plan B, first slice): `texmodel.components.Command`, `texmodel.package.Package`, `texmodel.types.Text`.
  A command is a class; its fields are its arguments (an optional field is keyword-only and TeX's one optional argument),
  its body is TeX in `<name>.tex` beside it or inline. `Package.render()` writes a deterministic `.sty` with a provenance
  comment per command; declarations are refused at class definition with `TM-M0xx` codes. `texmodel build` and
  `texmodel check` (`[tool.texmodel] package`, `output`) write and drift-check the generated files.
- `texmodel-build`: a second package in this repo (`harness/`) holding the compile and verify side; `texmodel` itself no
  longer spawns processes. Config for it moved to `[tool.texmodel-build]`.
- `texmodel_build.Compiler`: a thin `latexmk` driver (host, or `docker run` over an image) returning a typed
  `CompileResult` with parsed diagnostics (`TM-X0xx`), page and pass counts, probes and tool versions; ordered asset
  roots, font directories, `--epoch`, convergence diagnostics, `clean`. `texmodel-build` has `compile`, `build` (targets
  from `[tool.texmodel-build.targets]`), `clean`, `verify` and `doctor`.
- Verifier plugins (`texmodel_build.verifiers` entry points) with the rule that anything unconfirmable fails; an optional
  adapter over proof-pdf (`texmodel-build[proof-pdf]`).
- `texmodel.drift` and `texmodel.bundle`: byte-for-byte drift detection (stale, missing, orphaned) and a manifest copy that
  refuses if any source is missing.
