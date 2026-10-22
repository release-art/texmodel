# Roadmap: batches an agent can run unattended

Each batch is self-contained: goal, what it depends on, the decisions already made (so nobody has to ask), scope, and what
done looks like. Source of the ideas: `docs/texmodel-plan.md` §21a (item numbers below). Run batches in the order of the
dependency graph; batches in different lines touch different files and may run in separate worktrees, but several touch
`package.py`, `components.py` and `cli.py`, so merge one line at a time.

```
0 hygiene
A line:  A1 references ──> A2 emitter ──> A3 stub tests      A4 Comment node (independent)
B line:  B1 documents CLI        B2 measure         B3 grammar hatches
C line:  C1 scanner reach        C2 preamble types  C3 small types       C4 package schema + aliases
D line:  D1 source maps for .sty D2 doctor for .sty
Needs an owner decision first:  X1 data-driven render   X2 hand-edit semantics   X3 rules layer   X4 List
```

## Rules for every batch (the brief an agent starts from)

- Work in `/Users/ilo/Devel/Release.art/texmodel`. Read `README.md`, `CONTRIBUTING.md`, the plan sections named in the batch,
  and the modules named under "Touches". Do not commit, push or change GitHub settings.
- Conventions (they override defaults): explicit over implicit (named methods and enums, no name-based lookup, no magic
  strings); every `Enum` is decorated with `@enum.unique`; nothing is released, so docs, comments and `CHANGELOG.md`
  (`## [Unreleased]`) describe the current state only (no "changed", "no longer", "formerly"); errors are
  `DeclarationError(msg, code=, path=, hint=)` with a new stable `TM-xxxx` code (grep for the next free one); frozen
  dataclasses; no `Any` in public signatures; only `cli.py` prints; line length 120; docstrings cite plan ids; lean diffs,
  reuse what exists, no scaffolding for later.
- Tests: pytest, hypothesis where there is a law, `monkeypatch` (no manual `sys.path` edits), 100% coverage across both
  packages. Consumer-shaped tests use `tests/consumers/card_deck/` (synthetic, made-up data). **Never** add anything from a
  real or private deck or brand package to this repo.
- Done = all of these pass with no new warnings: `pdm run ruff format --check src harness tests`,
  `pdm run ruff check src harness tests`, `pdm run pyright`, `pdm run lint-imports`, `pdm run pytest` (100%),
  `pdm run pip-audit`, `TEXMODEL_REQUIRE_TEX=1 pdm run pytest -m tex --no-cov` (needs Docker).
- Update the README, `CHANGELOG.md`, and the plan (mark the item built with the date and say what is still open; add decision
  rows to §21). Report at the end: what changed, what was verified, what was not, failures included. If a decision turns out
  to be large or irreversible, stop, write the question and a recommended answer at the top of the report, and finish the
  parts that do not depend on it.

---

## 0. Hygiene before anything is published

**Goal.** Make sure nothing private can reach a public commit.
**Do.**
- `grep -rniE` the repo (excluding `.venv`, `.git`, `mutants`) for the private consumer's names (the deck and brand names appear in
  `docs/briefs/gate-b-report.md`, which is gitignored, and in `docs/texmodel-research-notes.md`); list every hit.
- Rewrite `docs/texmodel-research-notes.md` to describe the first consumer generically, or move the file to a gitignored path;
  keep the technical content.
- Check `git status --short -uall` and `.gitignore`: only generic files may be untracked-and-not-ignored.
**Done.** A short report listing each file with a private reference, and what was done. No code changes; run the gates only if
files outside `docs/` changed.

---

## A1. Typed references in bodies (plan 17)

**Goal.** A body can call another component by Python binding; a component of another package pulls its package in.
**Depends on.** Nothing (builds on `texmodel.body`). **Touches.** `body.py`, `components.py`, `package.py`,
`_internal/render.py`, README, tests.
**Decisions made.**
- API: a method on the component class, `Fact.call(*args)` for a command and `Box.begin(*args)` / `Box.end()` for an
  environment, available on `_Node` (so on every `Command` and `Environment` class). Each returns a frozen `Ref` body piece
  (a new member of `BodyPiece`).
- Arguments to `call` / `begin`: `Hole("name")` (renders `#name`, so it must be a field of the component being defined),
  a `Raw` (passes through), or a `str` (escaped as `Text`). Arity and the one optional argument are checked against the
  referenced class's `__tm_args__` when the piece is built (`TM-M026`); a `Hole` naming a missing field is the existing
  `TM-M009` at render.
- Resolution is lazy: the referenced class may be registered later than the body is defined, so `Ref` is turned into text
  (`\<prefix>Name{...}`) in `Package.render()`; registration-time lints skip a body that holds unresolved refs.
- A ref to a class not registered with any package is `TM-M019` (existing code, "not registered").
- Dependencies: the referenced class's package is recorded when `Package.command/environment` registers the class
  (`cls.__tm_package__`). `Package.requires` is the sorted tuple of other packages' names that its bodies reference
  (computed, not mutated). `render()` emits `\RequirePackage{other}` for them, merged and sorted with the packages that
  values need (M14). Works for an adopted package: only its name is needed. A cycle between packages is `TM-P007`.
- Plain strings with `#name` stay valid and unchanged; `check_references` (G2) still scans strings.
**Do not.** Add conditionals or loops to the vocabulary; read TeX back.
**Tests.** A body mixing strings and refs renders the expected `.sty`; arity/optional errors; cross-package ref adds a sorted
`\RequirePackage` once; adopted target; cycle refused; unregistered ref; golden for an example in `tests/examples/`
(`UPDATE_GOLDEN=1`, reviewed); compile suite builds the example.

## A2. Constructive emitter (plan 19)

**Depends on.** A1. **Touches.** `body.py`, `components.py`, tests, README.
**Decisions made.** New body pieces in `texmodel.body`, all frozen dataclasses: `Group(*pieces)` renders `{...}` (balanced by
construction); `Cs(name)` renders `\name` with a validated control word (letters and `@` only, else `TM-M027`); `Text(str)`
body piece is not needed: use `str` escaped via `Lit(str)` that escapes as `Text`. `Hole` and `Ref` from A1 are accepted
inside `Group`. Pieces may nest; the renderer flattens to text then applies each `TexRaw`'s whitespace policy as today
(a `Group` has no policy; policy belongs to `TexRaw`). Loops and conditions are plain Python in `body()`.
**Tests.** Balance holds for any nesting (hypothesis); invalid control words refused; `Lit` escapes; nested refs.
**Done.** Plus a README section "Generating a body" using a `Choice` loop that emits one branch per member.

## A3. Stubbed unit tests of generated code (plan 20)

**Depends on.** A1 (A2 optional). **Touches.** new `texmodel/testing.py` (public), `harness/.../testkit.py`, tests, README.
**Decisions made.**
- Fast tier (no TeX): `texmodel.testing.expand(node, stubs=[Fact])` walks a component's resolved body pieces with the node's
  field values and returns a list of `Call(name, args)` for each stubbed reference plus the literal text; deterministic.
- TeX tier: `Package.test_document(node, stub=[Fact])` returns a `.tex`: the real definition of the component under test
  (and of non-stubbed dependencies), a stub per stubbed command that does `\typeout{texmodel:probe:call=<name>(<args>)}`
  (arguments through `\detokenize`), and the node. `texmodel_build.testkit` gets `run_probes(compiler, tex) ->
  list[Measurement]` using the existing probe parser (C5a). No new log format.
**Tests.** Fast and TeX tiers agree on calls and arguments for the `card_deck` and `tests/examples` components; a stub's
arguments with specials survive.
**Not covered, and said so in the README.** Layout.

## A4. `Comment` node (plan 21)

**Goal.** A comment is a first-class piece: every line it renders is prefixed with `%`, and a subclass can fill a template from
its fields (an audit block above each card, a note explaining a body).
**Depends on.** Nothing. **Touches.** `body.py`, `components.py`, `plan.py`, `spec.py`, tests, README.
**Decisions made.**
- `Comment(text: str)` is a frozen dataclass in `texmodel.body`. It renders `text` (dedented, blank edges removed) one line per
  line, each prefixed `% ` (a blank line becomes `%`). Every line is prefixed, so a multi-line value cannot leak out of the
  comment. No escaping: a comment is not TeX.
- Subclasses declare fields and a `template`, the same way a `Command` declares fields:

  ```python
  class CardHeader(Comment):
      """The audit block above a card."""
      template = """
          Card: #name
          id:   #id
      """
      name: str
      id: str
  ```

  Holes are `#name` (as in bodies, M8); `##` is a literal `#`. A hole that is not a field, or a field the template never
  uses, is refused at class definition (`TM-M028`, same checks as bodies). A subclass needs no package registration: it
  claims no control sequence and is not part of the interface check.
- Two places to use it:
  1. As a body piece: `Comment` (or a subclass instance) in a body sequence renders its lines at that position. A `TRIM`
     piece's `%` rule already leaves comment lines alone.
  2. As a document node: a child of an environment or a top-level node of `Package.plan(...)` / `document(...)`. A comment is
     transparent to the grammar: it is not counted and does not break order, so a grammar never lists it. Its plan path is
     like any child's (`Card[3]/CardHeader[0]`), so the line is named in a diff.
- `Plan.edits(text, ignore_comments=False)`: with `True`, lines that are comments in both the plan and the file are not
  compared (the old regex tool skipped audit blocks the same way).
- `from_dict` / `to_dict` / `json_schema` know a `Comment` subclass as a child (`"type": "CardHeader"` with its fields).
**Tests.** Prefixing for multi-line and blank lines; a value containing `\n` stays inside the comment (hypothesis); hole
checks; transparency to the grammar (counts and order unchanged with comments interleaved); plan paths; `ignore_comments`;
data round trip. Card-deck consumer: replace the legacy audit comments in the equivalence test by `CardHeader` nodes and
stop stripping comments in `printed()` for the model side.

---

## B1. Documents in the CLI (plan 5, 3)

**Depends on.** Nothing. **Touches.** `cli.py`, `config.py`, `_internal/loader.py` (expose a public pointer loader, e.g.
`texmodel/pointer.py`, so the harness can use it without importing `_internal`), `harness/.../cli.py`, `compiler.py`, tests.
**Decisions made.**
- `texmodel render` with no pointer renders every `[tool.texmodel.documents]` entry to its path.
- `texmodel-build compile` and `build` accept `--plan <pointer>` (a pointer returning a `Plan`); diagnostics print their path.
  A target in `[tool.texmodel-build.targets.*]` may name `plan = "<pointer>"`.
- A package warning's `input line N` has no file: when the log has the `(./deck.tex` file stack at that point, use it; otherwise
  keep today's behaviour (documented in the code). Implement only if the stack is reliably recoverable from the log text;
  otherwise leave it and say so.
**Tests.** CLI tests with the fake toolchain; render-all; a target with a plan.

## B2. `Measure`: typed over-set (plan 2)

**Depends on.** Nothing (uses `PackageWarning`). **Touches.** `harness/.../diagnostics.py`, `_internal/logparse.py`, config,
tests, README.
**Decisions made.**
- A measure rule is data in `[tool.texmodel-build.measures.<name>]`: `package` (the package whose warning it reads),
  `pattern` (a regex with named groups `item`, `needs`, `has`, both lengths in pt), `kind = "fit"`. The parser turns a
  matching `PackageWarning` into a typed `Overset(item, needs_pt, has_pt, over_pt)` diagnostic (error severity, `TM-X031`),
  keeping the original warning. Lengths accept `pt`, `mm`, `cm`, `in` via `texmodel.types.Length`.
- Probe convention for packages that can adopt it: `texmodel:probe:fit.<item>=<needs>/<has>` produces the same `Overset`.
- With a `Plan`, `Overset.path` names the component (existing mapping).
**Tests.** Real-format log text from the synthetic `card_deck` package; bad regex refused at config load (`TM-D0xx`); both
sources produce the same diagnostic.

## B3. Grammar escape hatches (plan 4)

**Depends on.** Nothing. **Touches.** `components.py`, `spec.py`, `plan.py`, tests, README.
**Decisions made.**
- `Anywhere(X)` is a grammar term: zero or more `X` between any two other terms of the environment, and at its ends.
  Counted separately from the ordered runs. Several `Anywhere` terms are allowed.
- `Passthrough(tex: Raw)` is a node that renders its `tex` as one line; it is allowed only where a grammar lists it
  (`Passthrough.times.any()` or inside `Anywhere`). `from_dict` knows both (`"type": "Passthrough"`).
- Violations keep their codes; a misplaced child is `TM-C001` as now.
**Tests.** Hypothesis: any interleaving of `Anywhere` items among a valid ordered run validates; counts still enforced; plan
paths; `from_dict`/`to_dict` round trip; schema.

---

## C1. Adoption scanner reach (plan 8)

**Depends on.** Nothing. **Touches.** `_internal/scan.py`, `package.py`, `cli.py`, tests.
**Decisions made.**
- Also read `\newcommand*`, `\renewcommand`, `\DeclareRobustCommand`, `\NewDocumentCommand` / `\NewDocumentEnvironment` /
  `\DeclareDocumentCommand` (xparse argument spec: `m` required, `o` optional with default, others unsupported ->
  recorded as "unmodelled", never guessed). Signature comparison stays count plus first-optional.
- Present-but-undeclared names (public names of the prefix the sources define that the model does not declare) are reported by
  `check` as notes (`note TM-C012 \bbX defined, not declared`), failing only with `[tool.texmodel] undeclared = "error"`.
- A renewal of a declared name in the sources is a note (`TM-C013`, M10).
**Tests.** Table of declaration forms; unmodelled forms reported, not accepted; config key.

## C2. Typed preamble entries (plan 10)

**Depends on.** Nothing. **Touches.** `package.py` (or a new `preamble.py`), tests, README.
**Decisions made.** Entries are frozen dataclasses that render to one `Raw`: `PassOption(package, option)`,
`InputPath(*dirs)` (renders `\makeatletter\def\input@path{{...}}\makeatother`), `GraphicsPath(*dirs)` with the empty first
group kept explicit (`include_cwd=True` default), `RequireMetadata(**entries)` for `\DocumentMetadata`. `PreambleSlots` slots
accept `Raw | entry`. G3 ordering lints: `InputPath` must be in `before_package`, `GraphicsPath` in `after_package` (`TM-C008`).
**Tests.** Rendered text; ordering refusals; plan paths unchanged in shape.

## C3. Small types (plan 1, 9)

**Depends on.** Nothing. **Touches.** `types.py`, `components.py`, `spec.py`, tests.
**Decisions made.** `PdfString`: a field type that escapes for a PDF literal string (balanced parentheses required or
backslash-escaped, `\\`, non-ASCII left as is) and is TeX-safe when emitted inside `\pdfmanagement_add:nnn`-style calls;
`Value[Raw]` for a setting whose value is TeX (rendered `\renewcommand{\x}{<raw>}`, Raw's brace check). Both support
`from_dict`/schema. **Not** `List` (needs a decision, X4).

## C4. Package-level schema and renames (plan 15)

**Depends on.** Nothing. **Touches.** `spec.py`, `components.py`, `package.py`, `cli.py`, tests.
**Decisions made.** `json_schema(pkg)` returns one schema with `$defs` for every registered component and value;
`texmodel schema` writes it to `[tool.texmodel] schema_output`. `renamed_from`: a field keyword `field(renamed_from="old")`
accepted by `from_dict` (the old key loads, the new key is written by `to_dict`); recorded in the schema as `x-renamed-from`.
**Tests.** Schema validates example data with a JSON Schema validator (add as a dev dependency only if none is installed);
rename round trip.

---

## D1. Source maps for generated `.sty` (plan 11)

**Depends on.** Nothing. **Touches.** `package.py`, `plan.py`, `cli.py`, `_internal/render.py`, tests.
**Decisions made.** `Package.render_plan()` returns a `Plan` with one path per component (`Fact`, `FactGap`) and `header` /
`requires`; `render()` returns its text (byte-identical to today). `texmodel check` reports generated-file drift by path
(`changed generated/x.sty Fact: ...`) using the plan diff, with the existing stale/missing/orphaned output kept.
**Tests.** Goldens unchanged; a hand edit to a `.sty` is named by component.

## D2. `doctor` for packages (plan 14)

**Depends on.** Nothing. **Touches.** `harness/.../cli.py`, `compiler.py`, tests.
**Decisions made.** `texmodel-build doctor --sty <glob>...` scans `\RequirePackage` / `\usepackage` / `\LoadClass` /
`\tcbuselibrary` targets in the given files, asks the configured toolchain with `kpsewhich` which are missing, and prints the
list with the `tlmgr install` line. Exit 3 if any are missing. No network use.
**Tests.** Fake toolchain.

---

## Needs an owner decision first (do not start unattended)

- **X1 Data-driven rendering (plan 16).** Open: the shape of the declared field mapping (joins, slot order, policies),
  where it lives, and reopening the parked TOML frontend. Proposed: a `Mapping` object next to the components, `texmodel render
  --data file.toml <pointer>`. Needs a design review.
- **X2 Hand-edit semantics (plan 6).** Open: keyed children (path by id), the ignore-marker rule, the import hook. Needs the
  consumer's real workflow.
- **X3 Rules layer and placement (plan 7, D5, M5).** Open: the `@rule` API and severities. Needs a design review.
- **X4 `List[T]` fields (plan 1).** Open: how a list renders (separator, per-item wrapper, empty list). Needs a decision.
- **X5 Gate B closing.** A first-time author timing a new component, and a second consumer whose history has an escaping bug
  and an over-set card. Human work.

## Suggested order

0, then A1, A4, B1, B2, C1, C2, A2, B3, C3, C4, D1, D2, A3. A1 first because three batches need its references; the rest are
ordered so that batches touching `cli.py`/`package.py` do not run at the same time. Between batches: run the gates, read the
report, then start the next.
