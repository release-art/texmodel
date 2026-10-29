# Roadmap: one ordered backlog

What is left to do, in the order to do it. The order follows risk and demand: what makes the existing output or checks wrong
comes first, then what consumers have asked for, then what needs a decision, and last what waits for a second consumer to ask.
The specification is `docs/texmodel-plan.md`; `§21a N` below names an idea there, and `docs/known-limitations.md` says what does not work today. Items that touch `package.py`, `components.py` or
`cli.py` must not run at the same time.

## 1. Correctness and trust

Nothing open: what is found goes here first.

## 2. Asked for by a consumer

| # | Item | Notes | Size |
|---|---|---|---|
| 1 | **Output-change labelling** (K3, G7). `check` names the minor release that changed a generated file; the changelog marks such a release. | Consumers commit `.sty` files and need to know which upgrade moved them. Open: where the record lives so the installed package can read it (a table in `drift.py` kept with the changelog, or a marker in the changelog shipped as package data). | small |
| 2 | **Hand edits, the rest of it** (X2, §21a 5, 6, 18). `read_edits` and `Edit.fields` are built. Open: a `texmodel-build` command over `read_edits`; `Doc.apply(edits)` once the edits are trusted; settings (`Value`s) read by TeX (`\the\lbGap`, `\iflbFlag`, `\extractcolorspec`); a tree-aware diff (a move across environments reads as the close moved); a scan for a redefined stubbed macro; keyed children (a path by id), the ignore-marker rule and the import hook. | The first three need the consumer's real workflow; the last three change what a path means, so decide them together. | large |
| 3 | **A print page chosen at load time** (`ext.printpage`). A package option picks the sheet (a crop build and a trim-only preview), landscape swaps the trim, `showcrop` and its flag are written, and the page boxes follow the sheet chosen. | `ColourSpace` already owns the package's `\ProcessOptions`, so the two need one options block or a declared order. The margin model is settled: the consumer's margins are from the trim and its type area is the same in both sheets, as `Sheet.TRIM` keeps it. Ask the consumer for its hand-written page, boxes and options files when this starts, to read the design (they stay out of the repo). | medium |

## 3. Needs a decision first

| # | Item | Open question |
|---|---|---|
| 4 | **`Doc` with migrations** (§21a 14; plan C0, X1 to X10). `renamed_from` is built; a saved document whose declaration changed is not migrated. | Whether stored documents (a consumer keeping defaults written out) reach this before 1.0. If so, move it above 1 to 3. |

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
