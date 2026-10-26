# Roadmap: batches an agent can run unattended

Each batch is self-contained: goal, what it depends on, the decisions already made (so nobody has to ask), scope, and what
done looks like. Source of the ideas: `docs/texmodel-plan.md` §21a. Batches that touch `package.py`, `components.py` or `cli.py` must not
run at the same time.

```
No batch is ready to run unattended. Candidates, each small once an owner picks it:
  K1 a counter as a ValueKind (`\newcounter`; claims a counter namespace, so a package declares it and a part defining it is checked)
  K2 external sources checked both ways (a name a hand-written `.sty` defines that nothing declares, as a library's `TM-C012`)
  K3 output-change labelling (G7): `check` names the minor release that changed a generated file, the changelog marks it
Needs an owner decision first:  X1 data-driven render   X2 hand-edit semantics   X3 rules layer   X4 List   X5 Gate B
```

## Rules for every batch (the brief an agent starts from)

- Work in `/Users/ilo/Devel/Release.art/texmodel`. Read `README.md`, the guide in `docs/`, `CONTRIBUTING.md`, the plan sections named in the batch,
  and the modules named under "Touches". Do not commit, push or change GitHub settings.
- Conventions (they override defaults): explicit over implicit (named methods and enums, no name-based lookup, no magic
  strings); every `Enum` is decorated with `@enum.unique`; docs and comments describe the current state only (no "changed", "no longer", "formerly");
  `CHANGELOG.md` (`## [Unreleased]`) lists what differs from the last release under Added, Changed, Removed and Fixed; errors are
  `DeclarationError(msg, code=, path=, hint=)` with a new stable `TM-xxxx` code (grep for the next free one); frozen
  dataclasses; no `Any` in public signatures; only `cli.py` prints; line length 120; docstrings cite plan ids; lean diffs,
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

---

## Needs an owner decision first (do not start unattended)

- **X1 Data-driven rendering (plan 15).** Open: the shape of the declared field mapping (joins, slot order, policies),
  where it lives, and reopening the parked TOML frontend. Proposed: a `Mapping` object next to the components, `texmodel render
  --data file.toml <pointer>`. Needs a design review.
- **X2 Hand-edit semantics (plan 6).** Open: keyed children (path by id), the ignore-marker rule, the import hook, a
  `texmodel-build` command over `read_edits`, `Doc.apply(edits)`, settings read by TeX (`\the\lbGap`, `\extractcolorspec`), a
  tree-aware diff, a scan for a redefined stubbed macro. Needs the consumer's real workflow.
- **X3 Rules layer and placement (plan 7, D5, M5).** Open: the `@rule` API and severities. Needs a design review.
- **X4 `List[T]` fields (plan 1).** Open: how a list renders (separator, per-item wrapper, empty list). Needs a decision.
- **X5 Gate B closing.** A first-time author timing a new component, and a second consumer whose history has an escaping bug
  and an over-set card. Human work.

---

The first-release work (brand package family, the deck as a model, `v0.1.0`) is listed in `docs/texmodel-plan.md` §19.
