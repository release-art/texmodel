# Contributing

Issues and pull requests are welcome.

```zsh
pdm install
git config core.hooksPath .githooks   # the pre-commit hook runs the checks below
bin/autoformat.sh                     # ruff format, ruff check --fix, pyright, import-linter
bin/test.sh                           # pytest, 100% coverage gate
```

- Code is formatted and linted with ruff, type-checked with pyright (strict on `src`, 0 errors), runs on Python 3.15.
- Public API is the top-level modules of `src/texmodel` (and what `texmodel/__init__.py` re-exports); everything else
  lives in `texmodel/_internal/` and may change freely, as in pydantic. A new module goes in `_internal` unless users
  should import it (then add it to `PUBLIC` in `tests/test_texmodel/test_public_api.py` and document it).
- Only `cli.py` formats output; the library uses `logging` and `warnings` (plan E5).
- New behaviour comes with a test; add a line under `## [Unreleased]` in `CHANGELOG.md` for anything user-visible.
- Design lives in `docs/texmodel-plan.md`; requirement ids (e.g. `E1`) are what tests and commits cite.
