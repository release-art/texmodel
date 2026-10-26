# Roadmap: one ordered backlog

What is left to do, in the order to do it. The order follows risk and demand: what makes the existing output or checks wrong
comes first, then what consumers have asked for, then what needs a decision, and last what waits for a second consumer to ask.
The specification is `docs/texmodel-plan.md`; `§21a N` below names an idea there, and `docs/known-limitations.md` says what does not work today. Items that touch `package.py`, `components.py` or
`cli.py` must not run at the same time.

## 1. Correctness and trust

| # | Item | Why now | Size |
|---|---|---|---|
| 1 | **Diagnostic mapping** (§21a 3). A package warning's `input line N` has no file, so one raised inside another file is mislabelled. | A wrong answer from a diagnostic is worse than none. | small |
| 2 | **A flaky compile test.** `test_fatal_errors_are_explained_not_just_failed[missing_package.tex]` raised `ToolchainError` from latexmk once in a full run and passed alone. Find the shared state (the font cache, a parallel run). | A flaky required gate trains people to rerun it. | small |
| 3 | **A public-API snapshot in CI** (plan I2, A9; `griffe`). Every public module now has an `__all__`, so the snapshot is the list of those names and their signatures. | 0.4.0 removed names; the next removal should be a reviewed diff, not a surprise. | small |
| 4 | **Hide the rest of the plumbing** that is public by name only (`inline_text`, `text_of`, `call_line`, `spec_of`, `env_spec_of`, `value_spec_of`, `field_info`, `record_fields`, `FieldNotes`, `body_of`; listed in `NOT_API` in `tests/test_texmodel/test_public_api.py`). Needs `components.py` and `interface.py` split so the helpers move to `_internal` without a cycle. | The smaller the surface, the cheaper every later change. | medium |

## 2. Asked for by a consumer

| # | Item | Notes | Size |
|---|---|---|---|
| 5 | **Output-change labelling** (K3, G7). `check` names the minor release that changed a generated file; the changelog marks such a release. | Consumers commit `.sty` files and need to know which upgrade moved them. | small |
| 6 | **Hand edits, the rest of it** (X2, §21a 5, 6, 18). `read_edits` and `Edit.fields` are built. Open: a `texmodel-build` command over `read_edits`; `Doc.apply(edits)` once the edits are trusted; settings (`Value`s) read by TeX (`\the\lbGap`, `\iflbFlag`, `\extractcolorspec`); a tree-aware diff (a move across environments reads as the close moved); a scan for a redefined stubbed macro; keyed children (a path by id), the ignore-marker rule and the import hook. | The first three need the consumer's real workflow; the last three change what a path means, so decide them together. | large |
| 7 | **External sources checked both ways** (K2). A name a hand-written `.sty` defines that nothing declares is reported, as a library's `TM-C012` is. | Completes adoption for anyone keeping hand-written TeX. | medium |

## 3. Needs a decision first

| # | Item | Open question |
|---|---|---|
| 8 | **`Doc` with migrations** (§21a 14; plan C0, X1 to X10). `renamed_from` is built; a saved document whose declaration changed is not migrated. | Whether stored documents (a consumer keeping defaults written out) reach this before 1.0. If so, move it above 5 to 7. |

## 4. Waits for a second consumer to ask

Not started on purpose; each needs a design or a real workflow first.

- **Data-driven rendering** (X1, §21a 15): the shape of the field mapping, and whether the parked TOML frontend returns.
- **A rules layer and placement** (X3, §21a 7, D5, M5): the `@rule` API and severities.
- **`List[T]` fields** (X4, §21a 1): separator, per-item wrapper, empty list.
- **A counter as a `ValueKind`** (K1): claims a counter namespace.
- **Smaller ideas** (§21a 2, 4, 9 to 13, 16, 17, 19): `Measure` beyond `fit`, grammar interleaving, PDF strings and PDF/A, declared preamble slots, declared-only variants, consumer policies, the reference image's PDF/X and ICC gaps, constructive-body whitespace, stubs for settings, expl3 as its own `.sty`.
- **Gate B and Stage C** (plan §19; X5): a timed first-time author and a second consumer with an escaping bug and an over-set card; then migrations as releases, adoption beyond the minimal check, equivalence tests, `texmodel-print`, performance budgets and 1.0.
- **Trust levels, the injection corpus and the sandbox** (plan Z1 to Z3): needed before untrusted data may reach a `Raw` field.

---

## Rules for every item (the brief an agent starts from)

- Work in `/Users/ilo/Devel/Release.art/texmodel`. Read `README.md`, the guide in `docs/`, `CONTRIBUTING.md`, the plan sections named in the item,
  and the modules the item names. Do not commit, push or change GitHub settings.
- Conventions (they override defaults): explicit over implicit (named methods and enums, no name-based lookup, no magic
  strings); every `Enum` is decorated with `@enum.unique`; docs and comments describe the current state only (no "changed", "no longer", "formerly");
  `CHANGELOG.md` (`## [Unreleased]`) lists what differs from the last release under Added, Changed, Removed and Fixed; errors are
  `DeclarationError(msg, code=, path=, hint=)` with a new stable `TM-xxxx` code (grep for the next free one); frozen
  pydantic models (components) and dataclasses; no `Any` in public signatures; only `cli.py` prints; line length 120; docstrings cite plan ids; lean diffs,
  reuse what exists, no scaffolding for later.
- Tests: pytest, hypothesis where there is a law, `monkeypatch` (no manual `sys.path` edits), 100% coverage across both
  packages. Consumer-shaped tests use `tests/consumers/card_deck/` (synthetic, made-up data). **Never** add anything from a
  real or private deck or brand package to this repo.
- Done = all of these pass with no new warnings: `pdm run ruff format --check src tests`,
  `pdm run ruff check src tests`, `pdm run pyright`, `pdm run lint-imports`, `pdm run pytest` (100%),
  `pdm run pip-audit`, `TEXMODEL_REQUIRE_TEX=1 pdm run pytest -m tex --no-cov` (needs Docker).
- Update the guide, `CHANGELOG.md` and the plan (remove the item from §21a; add decision rows to §21). Report at the end: what
  changed, what was verified, what was not, failures included. If a decision turns out to be large or irreversible, stop,
  write the question and a recommended answer at the top of the report, and finish the parts that do not depend on it.
