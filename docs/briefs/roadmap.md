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
| 0 | **`texmodel.run`, async** (`docs/briefs/run.md`; built in texmodel, texpkg left). `texmodel.run` moves under one import root as `texmodel.run`, behind an exhaustive layers contract; one `texmodel` CLI; what starts a process is `async def`, with a timed-out or cancelled compile killing its child and container. First, so restore and `read_edits` land under the new name. | For the managing system that ingests hand edits inside an event loop. Decided: one CLI, `pytest-asyncio`, texpkg's helpers async. Touches `cli.py`. | medium |
| 1 | **Restore data from an edited document** (X2, §21a 5, 6, 18; `docs/briefs/hand-edits.md`). Given the document texmodel last wrote and the edited text, return the data that would have produced each edit (changed arguments as typed values, removed and commented-out nodes the grammar allows), checked by re-rendering, and every edit it cannot restore with its path and a reason. Built: `Plan.edits`, `Edit.fields`, `read_call`, `read_edits`, texpkg's refusal to overwrite. | The consumer's process is known (an LLM-generated deck, edited by hand in git, ingested on pull). Not needed: paths keyed by id (a card's id is a `Comment` beside it), settings read by TeX (layout is not edited), a diff that understands moves, a CLI. Decided (2026-10-29): every edit comes back, applied or with one `Reason`; after item 0. | medium |
| 2 | **The print page against the consumer's files.** Package options and `PrintPage` switches are built (`docs/briefs/print-page.md`). Left: read the consumer's `page.tex`, `boxes.tex` and `options.tex` and their landscape compile against it when they arrive (the files stay out of the repo), and settle anything they show. | They attach the files to their next reply. | small |

## 3. Waits for a second consumer to ask

Not started on purpose; each needs a design or a real workflow first.

- **Data-driven rendering** (X1, §21a 15): the shape of the field mapping, and whether the parked TOML frontend returns.
- **A rules layer and placement** (X3, §21a 7, D5, M5): the `@rule` API and severities.
- **`List[T]` fields** (X4, §21a 1): separator, per-item wrapper, empty list.
- **A counter as a `ValueKind`** (K1): claims a counter namespace.
- **Reports from a pipeline** (§21a 20): a typed table model over `tabularray`, charts embedded as PDF, data binding;
  the reference image needs `tabularray` first.
- **Smaller ideas** (§21a 2, 4, 9 to 13, 16, 17, 19): `Measure` beyond `fit`, grammar interleaving, PDF strings and PDF/A, declared preamble slots, declared-only variants, consumer policies, the reference image's PDF/X and ICC gaps, constructive-body whitespace, stubs for settings, expl3 as its own `.sty`.
- **Gate B and Stage C** (plan §19): a timed first-time author and a second consumer with an escaping bug and an over-set card; then adoption beyond the minimal check, equivalence tests, `texmodel-print`, performance budgets and 1.0.
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
