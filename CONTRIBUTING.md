# Contributing

Issues and pull requests are welcome.

```zsh
pdm install
git config core.hooksPath .githooks   # the pre-commit hook runs the checks below
bin/autoformat.sh                     # ruff format, ruff check --fix, pyright, import-linter
bin/test.sh                           # pytest, 100% coverage gate
```

- The container compile suite is `pytest -m tex`; it skips without an image that has `latexmk`, and `TEXMODEL_REQUIRE_TEX=1` turns
  that skip into a failure (`TEXMODEL_TEST_IMAGE` sets the image). `bin/test-image.sh` builds `texmodel-test` from
  `docker/test/Dockerfile`: the published reference image plus the few TeX packages the suite needs that it does not carry yet
  (`TEXMODEL_TEST_IMAGE=texmodel-test pdm run pytest -m tex`); CI uses it.
- Generated output is a contract (plan G7). `tests/fixtures/acme_cards/generated/acme-cards.sty` is the golden; if you change
  rendering on purpose, regenerate it and say so in the changelog:
  `pdm run python -c "import sys, pathlib; sys.path.insert(0, 'tests/fixtures'); import acme_cards as a; [pathlib.Path('tests/fixtures/acme_cards/generated', k).write_text(v) for k, v in a.pkg.files(version='0.1.0').items()]"`
- `tests/examples/` holds complete example packages with committed output (`expected/`); they double as documentation.
  After an intended output change: `UPDATE_GOLDEN=1 pdm run pytest tests/test_texmodel/test_examples.py`, review the diff.
- Every `enum.Enum` (and `StrEnum`) is decorated with `@enum.unique`.
- Code is formatted and linted with ruff, type-checked with pyright (strict on `src`, 0 errors), runs on Python 3.15.
- Two packages: `src/texmodel` (the library; never imports `texmodel_build` or spawns a process) and `src/texmodel_build`
  (the optional build side; only `_internal/spawn.py` may import `subprocess`). import-linter enforces both.
- Public API is the top-level modules of each package; everything else lives in `_internal/` and may change freely, as in
  pydantic. A new module goes in `_internal` unless users should import it (then add it to `PUBLIC` in that package's
  `test_public_api.py` and document it).
- Only `cli.py` formats output; the library uses `logging` and `warnings` (plan E5).
- New behaviour comes with a test; add a line under `## [Unreleased]` in `CHANGELOG.md` for anything user-visible.
- Docs are `README.md` (front page) and `docs/` (MkDocs: `pdm install -G docs`, then `pdm run mkdocs serve`). Their `python` blocks run in the test suite; fence an example that only illustrates as `py`.
- Design lives in `docs/texmodel-plan.md`; requirement ids (e.g. `E1`) are what tests and commits cite.
