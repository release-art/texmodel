# texmodel — research notes (2026-10-21)

Findings behind `texmodel-plan.md`, kept so the reasoning survives the move into the
project repo. Everything here was observed on 2026-10-21 unless a source is cited.
Nothing was built or run beyond read-only inspection.

## 1. `brainyboo-brand` LaTeX and deck-schema generation (the first consumer)

- "openapi" there is a **JSON Schema 2020-12** deck spec
  (`derived/schema/<version>/deck.schema.json`, 2,040 lines) generated from pydantic
  models in `src/brainy_boo_brand/latex/schema.py`; OpenAPI 3.1-compatible, no endpoints.
- Spec shape: `{brand_version, series, options, settings, cards[front, back]}`,
  discriminated by series; `x-latex-*` annotations carry macro, call template, argument
  types, placement, region order and a document skeleton.
- Generated `.sty` family (~5.7k lines, six files) from `tokens.json` through string
  templates and ~70 `.tex` fragments. Drift guards: G26 (fragments may not declare public
  names), G27 (schema byte-checked; earlier releases' examples migrate and validate).
  The family is also checked whole for undeclared control sequences.
- Strengths: one surface model (`surface.py`) and one argument declaration
  (`arguments.py`) feed `.sty`, schema, docs; series grammar enforced by *what exists*;
  migrations replayed from earlier examples.
- Gaps: **nothing converts a validated spec to `.tex`**; `edu-game-books` builds
  `deck.tex` from Jinja with hardcoded macros and grammar counts, then regex-parses its
  own output (`deck_tex_drift.py`, 423 lines); nothing consumes `deck.schema.json`; fit is
  only knowable by typesetting; no TeX in CI; migrations assumed compatible by default.
- One apparent inconsistency to verify: the Jinja comment says "3 labelled slots" while
  the condition is `loop.index > 4`.

## 2. Release.art brand folder (the second consumer)

`brand/` is only a token pack and guidelines; the LaTeX machinery is in
`src/release_art_cli/{latex,disclosure,pdfverify}`, `sources/latex/`, `derived/latex/`.
It is a **second independent implementation of the same pattern**: generated `.sty` from
tokens (committed, drift-guarded), compile driver (`ratex`/`ralatex` mirror
`bbtex`/`bblatex`), install and bundle, a PDF verifier, an enforceable naming policy.
Differences that shaped the plan: document classes (card with bleed, A4 report, Beamer
deck), CMYK and RGB variants of one name set, spot-colour separations, commercial
non-redistributable fonts, statutory text composed once for several targets, richer
verification (PDF/X-4 identity, TAC, rich-black, overprint, veraPDF), about 1,100 lines of
**hand-written** classes beside one generated `.sty`. Application specifics were
deliberately kept out of the plan; only workflow-level requirements were generalised.

## 3. Demand

No strong evidence of broad demand; treat as a tool built for your own use.
- PyLaTeX is the best-known generator: classes and context managers, untyped. No
  pydantic/dataclass-based LaTeX generator turned up.
- Jinja2 + escape filters is the DIY route; its HTML-oriented escaping fights LaTeX braces.
- Typst is the competition for new automated-report work (Thoughtworks Radar, April 2026
  calls it a modern successor for programmatic generation); LaTeX stays dominant in
  publishing.
- l3build is the closest "verifiable" tool, for TeX package authors.
- Evidence was anecdotal; no download or star counts were available.

## 4. PyLaTeX (MIT; ideas only)

Read 1.4.2 and current `master` (last commit 2024-07-23, i.e. dormant; ~9 small commits
past 1.4.2: formatting, doctests, a package-propagation fix #371, a type hint).
Borrowed (all in the plan): per-component package requirements (M14), distinct unescaped
type (T3), structural equality and constructor `repr` (D1), starred variants (M3a),
layout hints and declared option order (G1), `latexmk -c` cleaning (C7), executable
doctests (V3). Not borrowed: stringly-typed args, escaping by mutable flag, global mutable
config, raw subprocess exceptions, package propagation by tree mutation (its bug #331).

## 5. Typst (ideas only)

Reviewed function/styling/scripting/context docs, PDF export, package manifest, plus
man pages and the `tytanic` test runner. Borrowed: probes from `typst query` (C5a),
scoped overrides from set rules (D4a), compile-only/equivalence/reference test taxonomy
(V2a), PDF standards as validated combinations plus `--pages` (P2a, P2b), manifest
validation (U0), bounded passes with reported non-convergence (C1a). Not borrowed: show
rules, `context`, embedded scripting. **Unverified:** how Typst reports argument-type
errors; `tytanic`'s on-disk reference layout; CLI flag details came from man pages.

## 6. Reference container images (observed locally, arm64)

- `releaseart/lualatex` 0.2.0: TeX Live 2025, LuaHBTeX 1.22.0, ~750 MB, no Python,
  no Ghostscript.
- `releaseart/lualatex-python` 0.3.2: same TeX Live, Python 3.15.0, Ghostscript,
  veraPDF, ~1.26 GB, AGPL-3.0-or-later licence label.
- Source repo label: `release-art/proofpress`. Debian base; Perl 5.40 present.
- Neither has `latexmk`, `pdm`, `uv`, `qpdf`, `pdftoppm`. TeX Live 2025 is frozen, so a
  plain `tlmgr install` fails; plan: `apt-get install --no-install-recommends latexmk`
  after a dry run shows no Debian TeX packages, else `tlmgr --repository <historic>`.
- Docker Hub itself was not reachable from the session, so published tags and amd64
  availability are unchecked.
- Open: fonts and ICC profiles in the images; AGPL label vs the project's licence.

## 7. Name

`texmodel` chosen. PyPI free on 2026-10-21 (also free: texorm, texcontract, typedtex,
texspec, texschema, kerning, leading, pressroom, tympan, imposition, typesetter; taken:
texforge, galley, ligature, colophon, quoin, typecase). Not checked: GitHub namespace,
domains, trademarks. `texdoc` is an existing TeX Live command: avoid.

## 8. Open items carried into the plan

- Lua file access from `\directlua` inside the sandbox (verify in step B2).
- Snapshot library: `inline-snapshot` vs `syrupy` (C3). Mutation-testing tool and floor (A0).
- Exact built-in rule codes (B0).
- Image font/ICC content and licence compatibility (A1).
- Behaviour-pinning "compat profile" (PyLaTeX's `Version1` idea): not in the plan.
- TOML/YAML declaration frontend: parked, not planned.

## 9. Files

- `texmodel-plan.md` — the plan (v0.3). Authoritative.
- `superseded/texmodel-spec.md`, `texmodel-ux.md`, `texmodel-design-v2.md` — earlier
  drafts, kept for history; the plan replaces all three.
