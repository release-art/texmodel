# Agent brief: batch A4, the `Comment` node

You are an autonomous engineering agent working in `/Users/ilo/Devel/Release.art/texmodel`. Build one feature, run the gates,
and finish with an honest report. A report that says what was not done or not verified is worth more than a green result that
hides a gap.

## 0. Read first, in this order

1. `README.md`, `CONTRIBUTING.md`.
2. `docs/briefs/roadmap.md`: "Rules for every batch" and section **A4** (this is your spec; it has the decisions already made).
3. `docs/texmodel-plan.md`: N1, M1-M8, D1, D1a, D2, §21 (decisions log), §21a items 17, 18, 21.
4. Code: `src/texmodel/body.py`, `components.py`, `plan.py`, `spec.py`, `package.py`, `_internal/render.py`.
5. Tests to imitate: `tests/test_texmodel/test_body.py`, `test_refs.py`, `test_plan.py`, `test_spec.py`,
   `tests/consumers/card_deck/` with `tests/test_consumers/test_card_deck.py`.

## 1. State today (so you do not re-derive it)

- Python 3.15, monorepo: `texmodel` (`src/`, the library; never spawns a process) and `texmodel-build` (`harness/`; leave it
  alone for this batch). 303 tests pass at 100% coverage; the gates in section 4 are green on a clean tree.
- Components are frozen dataclasses: `Command` and `Environment` (`components.py`), built by `_build`, fields = TeX arguments.
  `Node = Command | Environment`. An environment's `children` is its grammar (`_grammar`, `_grammar_violations`); `validate()`
  returns every `Violation` with a path (`Card/CardBack[1]/LeadFact[2].text`); `render()` emits TeX.
- A body is what `body` / `begin` / `end` gives (`body.py`): a string, `TemplateRef`, `TexRaw`, `Ref` (`Fact.call(Hole("x"))`),
  or a sequence/iterator/generator of those. `TexRaw(body, whitespace=)` has a `Whitespace` policy (`KEEP`, `TRIM`);
  `Package(whitespace=)` is the default; `join()` writes the lines; `TRIM` leaves comment lines (starting with `%`) alone.
- `Package.plan(*nodes, settings=, options=, preamble=)` returns a `Plan` (`plan.py`): lines with the path of the node that
  wrote them (`node_lines`), `Plan.edits(text)`, `path_of(n)`, JSON round trip. `Package.document` is its text.
- `texmodel.spec`: `from_dict(cls, data)` / `to_dict(node)` / `json_schema(cls)` on pydantic; a child names its component with
  `"type"`; environments are pydantic models built from their grammar (`_model`, `_node`, `_path`).
- Adopted packages (`Package(..., adopted=True)`) only declare interfaces; they have no bodies.
- Synthetic consumer for consumer-shaped tests: `tests/consumers/card_deck/` (made-up cards, a hand-written `.sty`, a legacy
  generator in `legacy.py` that writes `% Card: ...` audit comments above each card).

## 2. The task (from roadmap A4; the decisions are made, do not re-open them)

`Comment(text)`: a frozen dataclass in `texmodel.body`. It renders `text` (dedented, blank edges removed) one line per line,
each prefixed `% ` (a blank line becomes `%`). Every line is prefixed, so a multi-line value cannot leak out of the comment.
No escaping (a comment is not TeX).

Subclasses declare fields and a `template`, the way a `Command` declares fields:

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

- Holes are `#name` (as in bodies, M8); `##` is a literal `#`. A hole that is not a field, or a field the template never uses,
  is refused at class definition with `TM-M028` (reuse the checks in `_internal/render.py`: `rewrite_body` style, but a comment
  has no `#1` rewrite, so write the substitution at render time).
- A subclass needs no package registration, claims no control sequence and is not part of the interface check
  (`check_interface`).
- Two uses:
  1. **Body piece:** a `Comment` (or subclass instance) in a body sequence renders its lines at that position. Add it to
     `BodyPiece`, `pieces_of`, `_source`/`join`. A `TRIM` piece's `%` rule already leaves comment lines alone; a comment piece
     has no whitespace policy of its own.
  2. **Document node:** a child of an environment, or a top-level node of `Package.plan(...)` / `document(...)`. It is
     transparent to the grammar: not counted, does not break order, never listed in a grammar. Its plan path is like any
     child's (`Card[3]/CardHeader[0]`); every line of a multi-line comment has that path.
- `Plan.edits(text, ignore_comments=False)`: with `True`, lines that are comments in both the plan and the file are not
  compared; a comment line changed into non-comment text (or the reverse) is still an edit.
- `from_dict` / `to_dict` / `json_schema` know a `Comment` subclass as a child (`"type": "CardHeader"` plus its fields). A
  bare `Comment` (`"type": "Comment"`, `"text"`) also loads.

Design guidance (these are choices left to you; take the simplest that fits the neighbouring code):
- Where `Comment` lives relative to `Node`: widen `Node` to `Command | Environment | Comment` or add a separate alias; keep
  pyright strict clean. `validate()` on a comment returns `[]`; `render()` returns its lines.
- Grammar matching must skip comments without changing the paths of other children (paths index the real position).
- Keep the diff lean: reuse `dataclass` building from `_build` only if it fits; a smaller dedicated builder is fine.

Out of scope: expl3, `Whitespace` changes, anything in `harness/`, new CLI commands, other roadmap batches.

## 3. Tests (what "done" must demonstrate)

- Prefixing: single and multi-line, blank lines, dedent, trailing blank lines; a value containing `\n` stays inside the comment
  (hypothesis).
- Template: holes filled from fields; `##`; unknown hole and unused field refused (`TM-M028`); a field missing from the call is
  the normal dataclass error.
- Body piece: a comment in a body sequence appears at its position in the `.sty` (golden or exact lines).
- Document node: transparent to the grammar (counts and order unchanged with comments interleaved, including as the first and
  last child); plan paths; `check_interface` unaffected; `validate()` clean.
- `Plan.edits(..., ignore_comments=True)` and its edge case (comment turned into text).
- Data: `from_dict` / `to_dict` round trip with a comment child inside an environment; `json_schema` lists it.
- Consumer: in `tests/test_consumers/test_card_deck.py`, replace the legacy audit comments by a `CardHeader` node per card in
  the model and compare with `printed()` without stripping comments on the model side (keep stripping on the legacy side only
  if the two audit formats cannot be made equal; say which in your report).
- If you add an example under `tests/examples/` (optional), regenerate goldens with
  `UPDATE_GOLDEN=1 pdm run pytest tests/test_texmodel/test_examples.py`, review the diff, and make sure the tex suite compiles it.

## 4. Definition of done

All of these pass with no new warnings:

```zsh
pdm run ruff format --check src harness tests
pdm run ruff check src harness tests
pdm run pyright                      # strict on src and harness/src
pdm run lint-imports
pdm run pytest                       # 100% coverage across both packages
pdm run pip-audit
TEXMODEL_REQUIRE_TEX=1 pdm run pytest -m tex --no-cov   # needs Docker
```

Also: README section (a short "Comments" example), a `CHANGELOG.md` entry under `## [Unreleased]`, plan §21a item 21 marked
built with the date and what is still open, and a decision row in §21 if you made a real choice. Docs and comments describe the
current state only: no "changed", "no longer", "formerly", no history.

## 5. Rules that override your defaults

- Do not commit, push, or change GitHub settings. Never add anything from a real or private deck or brand package to this repo;
  consumer-shaped tests use `tests/consumers/card_deck/` (synthetic).
- Explicit over implicit: named methods and enums, no operator tricks, no name-based lookup, no magic strings. Every
  `enum.Enum` / `StrEnum` is decorated with `@enum.unique`.
- Code reads like its neighbours: short docstrings citing plan ids, `DeclarationError(msg, code=, path=, hint=)` for every
  refusal with a new stable unused `TM-xxxx` code (grep for the next free one; `TM-M028` is reserved for this batch), frozen
  dataclasses, no `Any` in public signatures, no printing from the library (only `cli.py` prints), line length 120.
- Tests: pytest, hypothesis where there is a law, `monkeypatch` (no manual `sys.path` edits), golden files regenerated
  deliberately.
- Lean: shortest working diff, reuse what exists, no scaffolding for later. If a decision turns out to be large or
  irreversible (a public name change, removing a capability), stop, write the question and your recommended answer at the top of
  the report, and finish the parts that do not depend on it.

## 6. Report

At the end give: what you changed (files), what you verified (the commands above with their results and numbers), what you
could not verify, choices you made where the brief left room, anything that surprised you, and failures, plainly. Then name the
next batch from `docs/briefs/roadmap.md` (suggested order: A4, B1, B2, C1, C2, A2, B3, C3, C4, D1, D2, A3).
