# Agent brief: batch E1, expl3 as a syntax mode and verbatim library blocks

Status: built 2026-10-22 (all ten decisions; tests and gates as listed below).

Work in `/Users/ilo/Devel/Release.art/texmodel`. Read `README.md`, `CONTRIBUTING.md`, `docs/briefs/roadmap.md` ("Rules for every
batch" and "First integration and first release"), `docs/texmodel-plan.md` (M8, §21a items 12, 17, 18, 19, 20), and the
code: `src/texmodel/body.py`, `components.py`, `package.py`, `preamble.py`, `testing.py`, `_internal/render.py`,
`harness/src/texmodel_build/testkit.py`. Do not commit, push or change GitHub settings. Never put anything from a real or
private deck or brand package in this repo; consumer-shaped tests use `tests/consumers/card_deck/` (synthetic).

## Why

The first real consumer's brand package family holds algorithmic expl3: about 120 lines of title-fitting code (private
`\fp_…`, `\seq_…`, `\clist_…` registers, loops, a sort, one entry macro that LaTeX2e code calls), a 4-line `\ExplSyntaxOn`
block that wraps two `\newcommand`s, and `\pdfmanagement_add:nnn` for the PDF Info strings. texmodel must be able to carry
that code without typing it.

## Decisions made (do not re-open)

1. **expl3 is a syntax mode and a source kind, not a typed language.** No typed vocabulary of l3 functions, no Python
   wrappers for variables, loops or sorts. Reason: those are algorithms; Python calls add no checking over them and l3
   reports undefined or mis-typed functions at compile time.
2. **No TeX parser.** Syntax and interface are verified by Python tests that compile the code with lualatex and assert on the
   result (the reference image, `run_probes`, plan paths). The only static checks are the cheap certain ones below. Keep every
   such check behind one small function, so a parser could replace it later (memory note `project-tex-parser-option`).
3. **`Syntax`**: `@enum.unique` enum in `texmodel.body`, `LATEX2E` (default) and `EXPL3`. A `TexRaw` takes `syntax=`. A body
   (all its pieces) has one syntax; mixing is refused (`TM-M031`). In `EXPL3` the generated definition is wrapped in
   `\ExplSyntaxOn` / `\ExplSyntaxOff`, no `%` is added at line ends (the piece's `Whitespace` is ignored), a `Lit` writes `~`
   for a space, and `Cs` and `cs=` accept expl3 names.
4. **`Cs(name, syntax=Syntax.LATEX2E)`** and a component's `cs`: LATEX2E keeps letters and `@` (`TM-M027`); EXPL3 accepts
   `[A-Za-z@_:]+`. A class that uses an expl3 `cs` says so with `syntax = Syntax.EXPL3`.
5. **Library blocks**: `Package.library(name, source, *, syntax=Syntax.LATEX2E) -> Library`. `source` is a string or a
   `TemplateRef` (resolved like a body's). It is emitted **verbatim**: dedented, blank edges removed, no `%` added, **no `#name`
   rewriting** (`#1` and `##1` pass through as written), in registration order among the package's items, wrapped in
   `\ExplSyntaxOn` / `\ExplSyntaxOff` for `EXPL3`, with a provenance comment like a component's. In `render_plan()` every line of
   a block has the block's name as its path. `Library` is a frozen dataclass. Block names are unique (`TM-M007`).
6. **A component defined by a block**: `defined_by = <Library>` on the class. It is declared (name, arguments, `cs`), claims its
   control sequence, can be called with `call()` / `open()` / `close()` from other bodies (typed, arity-checked), and renders no
   `\newcommand`. It must have no body (`TM-M032`), and the block must belong to the same package (`TM-M033`).
7. **Static lints, only these**: braces balanced in a block (`types.balanced`); no `\ExplSyntaxOn` / `\ExplSyntaxOff` inside
   an `EXPL3` block (texmodel writes them; `TM-M034`).
8. **Compile-based verification** (part of this batch, not optional):
   - `texmodel.testing.export_probes(package) -> str`: TeX (for `PreambleSlots.after_package`) that, for every component
     defined by a block, writes `texmodel:probe:def.<cs>=yes|no` (`\ifcsname`) and `texmodel:probe:arity.<cs>=<n>` (the number
     of `#` parameters in `\meaning`'s text before `->`, `?` when `\meaning` is not a plain `macro:`).
   - `texmodel.testing.check_exports(package, probes: Mapping[str, str]) -> list[Violation]`: `TM-C010` for `no`, `TM-C011`
     for an arity that differs from the declared one (an optional first argument counts, `?` is existence-only).
   - `texmodel_build.testkit.check_library(compiler, package, files=None) -> list[Violation]`: builds the document with
     `Package.test_document`, compiles it with `run_probes`, then `check_exports`.
9. **`PdfInfo(**entries)`** in `texmodel.preamble` (a typed entry like `PassOption`): each entry `Key=value` writes
   `\csname pdfmanagement_add:nnn\endcsname{Info}{Key}{(\detokenize{<pdf_escape(value)>})}`. This route is verified against
   a hostile corpus in `tests/test_texmodel/test_pdf_string.py` (`pdfmanagement`). Keys are letters only. Slots:
   `before_package` or `after_package`. It needs `\DocumentMetadata`, so a document with a `PdfInfo` and no
   `RequireMetadata` in `before_class` is refused with a plan path (`TM-C009`). No expl3 syntax appears in a document.
10. **Std header**: add `FpEval` (`cs = "fpeval"`, one `Raw` argument `expr`) to `texmodel.std.latex`, and its sample to
    `tests/test_std/test_headers.py`. Nothing else is added to `texmodel.std` for expl3.

## Tests (what "done" must show)

- Each decision above, including refusals (`TM-M031`-`M034`, `TM-C009`) with their paths.
- Verbatim blocks: `#1` and `##1` survive; the rendered `.sty` equals the expected text exactly; golden for one example under
  `tests/examples/` (regenerate with `UPDATE_GOLDEN=1`, review the diff, compile it in the tex suite).
- Compile-based (mark `tex`, reference image from `TEXMODEL_TEST_IMAGE`; they must pass with `TEXMODEL_REQUIRE_TEX=1`):
  a valid EXPL3 block compiles and its exports are `yes` with the right arity; a block with a syntax error (a missing
  argument, an undefined `\fp_…` function) makes the compile fail and the error's `path` is the block's name; a missing export
  gives `TM-C010`; a wrong arity gives `TM-C011`; a `defined_by` component called from a generated body expands correctly.
- A behaviour test in the synthetic consumer: add a small algorithm block to `tests/consumers/card_deck/` (for example a font
  size from a width with `\fp_eval:n` and rounding) and assert its result through probes. Invent the numbers; copy nothing real.
- `PdfInfo`: a tex test with `RequireMetadata` + `PdfInfo` reads the 16-string corpus back with pikepdf.

## Definition of done

The gates in the roadmap's rules pass (ruff, pyright, import-linter, pytest at 100%, pip-audit, and
`TEXMODEL_TEST_IMAGE=texmodel-test TEXMODEL_REQUIRE_TEX=1 pdm run pytest -m tex`; build the image with `bin/test-image.sh`).
Update README (a short "expl3 and library blocks" section), `CHANGELOG.md`, the plan (§21a item 12 and 18 notes; decision
rows in §21), and this brief's status line. Docs and comments describe the current state only.

## Out of scope

A typed l3 vocabulary; a TeX or expl3 parser or definition scanner; porting any real brand code; `expl3` in documents beyond
`PdfInfo`; the data-driven render (X1).

## Report

What changed (files), the gates with their results and numbers, what you could not verify, choices you made where this brief
left room, surprises, failures, plainly.
