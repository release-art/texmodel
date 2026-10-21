# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Compile engine (plan A1): `texmodel.Compiler` runs `latexmk` with LuaLaTeX on the host or in the reference container
  (no network, read-only root, limits), returning a typed `CompileResult` with parsed diagnostics (`TM-X0xx`), page and
  pass counts, probes, and image/engine/latexmk versions. Reproducible mode (`epoch`), content-addressed compile cache,
  ordered asset roots, convergence diagnostics, `clean`.
- `texmodel compile`, `build` (targets from `[tool.texmodel.targets]`), `clean`; `doctor` probes the configured image.
