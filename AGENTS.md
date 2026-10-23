# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project

`texmodel`: typed models of LaTeX document families, in Python 3.15. A package is declared as classes (`Command`,
`Environment`, `Value[T]`) or as parts of hand-written TeX (`Package.library`), and rendered to a deterministic `.sty`; documents are
trees of those classes; a JSON Schema, drift checks and typed compile diagnostics come from the same declarations.
`src/texmodel` is the library (never spawns a process); `src/texmodel_build` is the optional `latexmk` driver and verifiers.
[README.md](README.md) is the reference, [docs/cookbook.md](docs/cookbook.md) the worked examples (run by the tests),
[docs/texmodel-plan.md](docs/texmodel-plan.md) the target spec and decisions log (§21), [docs/known-limitations.md](docs/known-limitations.md)
what it does not do, [docs/briefs/roadmap.md](docs/briefs/roadmap.md) the batches and the rules for an agent's brief.

**Pre-1.0:** no backward compatibility for the Python API, the CLI, the configuration or the generated output: rename or remove
directly. List every such change under `Changed` or `Removed` in `CHANGELOG.md`; a patch release never changes generated output (G7).

## Principles

- Follow the Zen of Python (`python -c "import this"`). Explicit, simple and flat code is better than clever code; named
  methods and enums, nothing found by name or inferred silently.
- DRY: reuse what exists (`grep` first) before adding anything. Delete what a change makes dead.
- Keep changes small and focused. No speculative abstractions, options or dependencies.
- Keep docs (README, cookbook, docstrings, comments, this file) brief. Comments say *why*, not *what*. Docs and comments
  describe the current state: no "changed", "no longer", "formerly" (the changelog is where change is told).
- Long strings (TeX, expected output, messages) are multi-line constants, `textwrap.dedent(...).strip()` or triple-quoted raw
  strings, not implicit concatenation.
- When a change alters behaviour, commands or configuration, update in the same change: the README, the cookbook if an
  example is affected, `docs/known-limitations.md`, the plan's decisions log (§21; requirement ids like `M8` are what tests and
  commits cite), and `CHANGELOG.md` under `## [Unreleased]`.
- **Nothing real or private enters this repo.** No customer, brand, deck or person's name, no real package, no real data: examples,
  tests and docs use the synthetic `acme` / `ac` packages and `tests/consumers/card_deck/`. A defect found in a real package becomes a
  synthetic test that shows it.
- Known limitations and bugs found while working are logged in `docs/known-limitations.md`; fix one only inside its task, and
  say so.

## Quality gates (mandatory)

Every change must pass all of these before it counts as done:

```bash
pdm run ruff format --check src tests
pdm run ruff check src tests
pdm run pyright                 # strict on src, 0 errors
pdm run lint-imports            # the package contracts (below)
pdm run pytest                  # coverage over both packages must stay at 100%
TEXMODEL_REQUIRE_TEX=1 pdm run pytest -m tex --no-cov   # when output, the scan or TeX written by the library changed (needs the reference image: bin/test-image.sh)
```

- `bin/autoformat.sh` formats, fixes what ruff can and runs pyright and import-linter; `.githooks/pre-commit` runs the gates
  (`git config core.hooksPath .githooks`).
- Judge each gate by its exit code, never by grepping its output. The full pytest run takes a minute and a half: run the
  files you touched first (`pdm run pytest tests/test_texmodel/test_x.py --no-cov`), the whole suite last.
- **Output that TeX must accept is proved by compiling, not by comparing text.** A rendering change needs a compile (the `tex`
  tests) as well as a golden. Goldens: `tests/fixtures/acme_cards/generated/` and `tests/examples/*/expected/`; after an
  intended change `UPDATE_GOLDEN=1 pdm run pytest tests/test_texmodel/test_examples.py`, then read the diff.
- Do not weaken the gates to make them pass. No `# pragma: no cover`, no blanket `# noqa` or `# type: ignore`, no loosened
  config. A `# noqa: CODE` or `# pyright: ignore[rule]` is narrow, rare and has its reason in the code (see the existing ones).
- Every new code path needs a test; new behaviour needs one that fails without it. In your summary say which gates you ran and
  which you did not (and whether the `tex` tests ran).
- Examples in `README.md` and `docs/cookbook.md`: the cookbook's `python` blocks run in `tests/test_docs.py`; keep them runnable.

## Package layout (pydantic pattern)

- Public modules sit at the top level of `texmodel/` and `texmodel_build/`; `_internal/` is what we deliberately hide
  (scanning, rendering helpers, value text, process spawning). A new module goes in `_internal` unless users should import it;
  then add it to `PUBLIC` in `tests/test_texmodel/test_public_api.py` and document it.
- `texmodel` never imports `texmodel_build` or spawns a process; only `texmodel_build/_internal/spawn.py` imports `subprocess`;
  only `cli.py` prints or formats output (the library uses `logging` and `warnings`). `lint-imports` enforces these.
- Keep the public surface small. Keep the version in the git tag only (the build reads it; the maintainer tags).

## Conventions

- Enums: mark every `Enum`/`StrEnum` `@enum.unique`, unless there is a stated reason not to.
- Errors: `DeclarationError(message, code="TM-Mxxx", path=, hint=)` (or `Violation` for a document problem) with a **new, stable
  code**: `grep -rhoE "TM-[A-Z][0-9]+" src | sort -u` for the next free one; a code is never reused. Say what is wrong, where
  (class and field), and the fix.
- Components and values are frozen dataclasses; output is a pure function of the declaration: no clocks, hashes, set or dict
  order in what is rendered. A `Value` is a `ValueKind` (data), not a branch in the renderer.
- Optional fields are written `arg(default=...)` so a type checker reads them as keyword-only.
- Pydantic is used at the data boundary (`spec`, `KeyVals`, `library(fill=)` models); component classes stay stdlib dataclasses.
  Lax coercion is fine: pyright catches mismatches at the source.
- Scanning TeX is regex-level and honest about it (a name defined another way counts as missing); it never silently accepts.
  Reading hand-written TeX beyond that is parked (plan N1); raise it only if the work needs it.
- Tests: pytest in `tests/`, `hypothesis` where there is a law, `monkeypatch` (no manual `sys.path` edits), temp projects under
  `tmp_path`. Consumer-shaped tests use `tests/consumers/card_deck/` (synthetic data). A test file past ~800 lines becomes a package.
- Dependencies: `pdm add` (runtime) or `pdm add -dG dev` so `pdm.lock` stays in sync.

## Working with the maintainer

- What to build next is [docs/briefs/roadmap.md](docs/briefs/roadmap.md) and the plan's §19 and §21a; ask before working outside
  the task, and for a design choice the task leaves open, propose it rather than picking silently.
- Git is the maintainer's: only read-only commands (`status`, `diff`, `log`, `show`). No `add`, `commit`, `restore`,
  `checkout`, `stash`, `reset`, `tag` or `push` unless explicitly asked. Releasing (the changelog section, the tag, the push) is theirs.
- Uncommitted changes aren't yours: the maintainer and other agents work in parallel. Read `git status` and `git diff` before
  starting, build on what is there, never revert it. If you break or override something of theirs, say so at once and restore it.
- Scratch files (scripts, logs, outputs) go in your scratchpad, never in the repo.
- Ask before a change to the public API, the generated output of existing packages or an error code's meaning beyond what was
  agreed: show the finding, propose, then build.
- Verify against real TeX rather than assuming; record real compiler output before writing a parser or a lint for it.
- Briefing another agent: the rules every brief repeats are in `docs/briefs/roadmap.md`; a brief carries only what is particular to its task.

## Development environment

- `pdm install`; run tools as `pdm run ...` or `.venv/bin/...`. The compile suite needs the reference image
  (`bin/test-image.sh`, then `TEXMODEL_TEST_IMAGE=texmodel-test`) or a local TeX Live with `latexmk` (LuaLaTeX).
- Python is 3.15 only; `.python-version` names it.

## Known traps

- `ruff format` rewrites lines after you edit them: re-read before a second `str.replace`-style edit, and keep lines at 120
  (docstrings too: E501 applies).
- LaTeX reads the first word inside `\ProvidesPackage{name}[...]` as a date: text that looks right can still be a TeX error.
  This is why rendering features are compiled, not only compared.
- Real TeX tests may run for minutes the first time (the image, fonts, caches): a long run is not a hang, check `ps`.
- Coverage reports an impossible miss after a same-size rewrite: delete `__pycache__` (a stale `.pyc` with old line numbers).
