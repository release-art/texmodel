# texmodel — project plan (consolidated, v0.3)

Supersedes `texmodel-spec.md`, `texmodel-ux.md` and `texmodel-design-v2.md` (moved to
`superseded/`). One document: what it is, how it is used, what it must do, in what
order it is built. Requirement ids are grouped by area and are the ids tests will cite
(`@covers("X3")`): O objectives, N non-goals, M components, T types, D documents,
G generation, C compile, V verification, S schema, I API contract, E errors, L plugins,
B standard library, Z security, X versions, P print extra, U daily use, W engineering,
A acceptance.

*texmodel* is the project name (decided 2026-10-21; PyPI name free at the time, GitHub
namespace, domains and trademarks not yet checked). The project is **application-agnostic**: it knows
nothing about any brand, deck or business domain.

---

## 1. Purpose

A typed, declarative, verifiable model layer for LaTeX, in the spirit of an ORM:
define the interface of a document family once in Python types, write macro bodies as
real TeX, and get everything else — the `.sty`, JSON Schema, reference docs, tests,
migrations, a strict document API, structured compile results — derived and checked.

**Why.** Two unrelated projects independently built the same machinery by hand
(generated package, compile driver, install/bundle, drift check, PDF verifier, naming
policy, migrations). Their failure modes are the same and silent: interface drift
between macro, generator, docs and schema; injection and escaping bugs; ordering
rules known only to the author; errors that surface as log text far from the cause.

### Objectives

- O1 One declaration per component; every artefact derives from it.
- O2 Type-checked construction; untrusted text escaped by type.
- O3 Structural validity checked before any TeX runs.
- O4 Compilation returns structured results.
- O5 Every layer is testable; TeX layers are testable in the reference container.
- O6 Strict, stable specs: JSON Schema 2020-12 (OpenAPI 3.1 embeddable), versioned,
  migratable.
- O7 Deterministic output: same input, byte-identical `.tex`/`.sty`.
- O8 A pleasant daily loop: small diffs, fast TeX-less feedback, clear errors.

### Non-goals

- N1 Not a TeX parser, macro expander or AST of existing TeX. We model *interfaces*; TeX we generate may be built from typed
  pieces (§21a items 17, 19), but TeX we did not write is never read back into a tree.
- N2 No layout solver; whether content fits is *measured* by TeX (C5).
- N3 Not a replacement for writing LaTeX: bodies are TeX, hand-written TeX can be
  adopted (M9).
- N4 No TOML/YAML declaration frontend (parked idea for a later major, not planned).
- N5 No guarantee of good typography; only well-formed, conformant, as declared.

---

## 2. Vocabulary

| Term | Meaning |
|---|---|
| **Component** | a Command, Environment or Value declaration |
| **Type** | what a field holds (`Text`, `Length`, `Colour`, …); the *only* extension point |
| **Package** | the container: components + bodies, rendering to a `.sty`/`.cls` |
| **Doc** | an immutable tree built from component classes; renders to `.tex` |
| **Spec** | a Doc as data (JSON); `doc.to_dict()` ≡ spec, `Doc.from_dict()` validates |
| **Body** | the TeX implementing a Command/Environment, given explicitly: a string, a method returning one, or a `TemplateRef` to a file |
| **Rule** | a pure check over a Doc returning structured violations |
| **Target** | a named build: spec + engine + variant + verifier profile |
| **Release** | a frozen version: schema, examples, migration chain |

ORM mapping: model ↔ Component; column type ↔ Type; bound parameter ↔ escaping at the
type boundary; dialect ↔ engine profile; DDL ↔ package render; session/unit of work ↔
Doc; migrations ↔ chain; reflection ↔ schema/docs; EXPLAIN ↔ `show` (plan).

---

## 3. Authoring model

### 3.1 Three components

- M1 **Command**, **Environment**, **Value[T]** are the only components. `Value[T]`
  covers settings, lengths, colours, toggles, counters and options; the type says
  which. Anything else (fonts, spot colours, snippets, pgf styles, colour cycles,
  role tables) is a *type*, never a new kind.
- M2 A component's Python signature is its interface. Fields are annotated; docs come
  from the class docstring and `field(doc=…)` (texmodel's own `field`, lowercase like
  `dataclasses.field`, also carrying `renamed_from`, X3). **Optional arguments are
  keyword-only in Python** (`T | None = default`) and come after the required ones, as
  Python requires; the renderer emits them where TeX needs them (`\newcommand` allows
  one optional argument, first). So `class Slot: text: Text; label: Text | None = None`
  is called `Slot("A soft woof.", label="Sound")` and renders `\acSlot[Sound]{A soft woof.}`.
  TeX argument order is derived from the declaration, never written twice.
- M3 Invalid layouts are refused at class definition: more than one optional argument
  (a `\newcommand` limit), `xparse` key-value arguments (unsupported v1), duplicate or
  reserved names — with a message naming class and field.
- M3a **Starred forms are supported** as a declared variant (`starred=True` on a
  Command or Environment gives `\name*` / `\begin{name*}` with the same signature).
  Common in real TeX (`\section*`, `table*`) and met immediately by adoption scanning
  (M9). The namespace policy, rules and schema treat it as the same component with a
  boolean `star` field.
- M1a **How each component renders.** A `Command` becomes `\newcommand` (body: M8);
  an `Environment` becomes `\newenvironment` with two bodies, `begin` and `end` (M8; the
  arguments belong to `begin`, TeX gives `end` none); a `Value[T]` needs no body, its type decides the
  declaration (`\newcommand` for text and options, `\newlength`, `\definecolor`,
  `\newif`, `\newcounter`) and its `default` is an *instance of the type*
  (`default = Length("2mm")`, `default = CMYK(0, 0, 0, .95)`), which the type checker
  and the validator both see. A missing body, or a `TemplateRef` to a file that cannot be read, is
  an error naming the class and the path, never a silent empty body.
- M4 **Grammar is one expression**: `children = [Name, Fact.times(2, 3), Slot.times(3)]`.
  A bare class means exactly one; `X.times(to)` allows 0 to `to`; `X.times(from_, to)`
  allows `from_` to `to`, and `to=None` means no upper limit (`X.times(2, None)` is two or
  more); `X.times(1)` is optional, `X.times.any()` any number (0 or more),
  `X.times.at_least_one()` one or more. This is the
  order, the counts and the placement of children. A static type
  checker verifies each child *is* an allowed component, not the counts or order
  (Python's types cannot express them); those are checked by `validate()` at
  construction time of the Doc, with the path of the offending child.
- M5 **Placement**: `Preamble`, `Document`, or `in(Env)` (inferred from `children`
  when possible). Misplacement is a violation naming the rule and reason.

### 3.2 Naming (convention over configuration)

- M6 One `Namespace` policy per package (data): prefix, case per kind (command,
  environment, colour, conditional, length, style, internal), optional lints (spelling
  list, initialisms, setter-vs-selector, no CTAN shadowing). Defaults are sane:
  `Fact` → `\acFact`; `FactGap` → `\acFactGap`; `Ink` → colour `ac-ink`;
  Python/JSON key `fact_gap`. One rule per mapping, round-trip tested.
- M7 A public-name collision across the registered family is an error at
  registration, not at `\begin{document}`.

### 3.3 Bodies

- M8 **A body is real TeX, given explicitly; nothing is found by name** (explicit is better
  than implicit). A component defines `body` (an Environment: `begin` and `end`) as:
  a string (dedented, so a raw triple-quoted string reads as it renders); a method
  returning a string; or a `TemplateRef(path)`, or a method returning one. A
  `TemplateRef` is read when the class is defined; a relative path is relative to the
  module that defines the class, so it works wherever the package is installed. A method
  is read once, at class definition, with no instance (`self` is `None`): it returns
  constant TeX and cannot depend on field values (those are `#name` holes). A field
  named `body`, `begin` or `end` is a field, not a body. Shared includes are ordinary TeX
  (`\input`) or a shared `TemplateRef`; there is no implicit include rule.
  - `#name` is the argument of that name (rewritten to `#1`…); `##` is a literal `#`.
  - Everything else is literal TeX. Public names must exist in the registry.
    Internals (`\ac@x`) need no declaration but must be *defined* in some body.
  - A body may declare `syntax = latex2e | expl3`.
  - Lint: balanced braces, no stray `%` line eating, every hole is a declared arg and
    every arg is used (or marked unused), no public-name declaration, no
    `\ProvidesPackage` date-slot misuse (G3).

### 3.4 Adopting hand-written TeX

- M9 **Conformance mode.** A hand-written `.cls`/`.sty` is registered with a manifest of
  its public surface (names, kinds, arities, placement). The scanner reads only
  declaration forms we model; it fails on declared-but-missing, present-but-undeclared,
  arity mismatch, name outside the namespace policy; anything unrecognised is reported
  and never silently accepted. The manifest is authoritative. Adopted and generated
  files share the same namespace and undeclared-name checks.
- M10 A document redefining a registered public name is flagged (a renewal of an
  undeclared name is a declaration by another route).

### 3.5 Packages and classes

- M11 `Package(name, prefix, engine, kind="package"|"class", base=…)`. `kind="class"`
  adds class options and `\LoadClass`. Document shape is not assumed: prose, fixed
  canvas slides and small bleeding pieces must all be expressible.
- M12 Layering is a DAG (`requires`/`layer`); cycles are errors. `graphlib` orders it.
- M13 **Engine capabilities**: packages declare `needs = {…}`; the engine profile
  provides them; a mismatch is a model-time error and a generated `\PackageError`
  guard in the output. v1 engine: lualatex only (profile abstraction in place).
- M14 **Third-party package requirements are declared and collected.** A component
  declares `needs_packages = ["tikz", "xcolor"]` (with options). A Package's required
  set is the pure union over its components (no tree mutation); the rendered file emits
  exactly those `\RequirePackage` lines in a stable order, and a Doc using a component
  inherits its requirements for document preambles. Lint: a body that uses a command
  from a package it did not declare fails `check` (scan limited to a maintained table
  of well-known packages' commands; anything unknown is not flagged). Option clashes
  between components requiring the same package are an error, not a silent merge.
  Rationale (PyLaTeX issue #331, fixed in master as #371): its requirements are
  propagated by mutating the tree upward, and packages used by cells nested inside a
  table were lost until the fix flattened the tree by hand. Computing the union purely
  from declarations removes that class of bug; a property test builds nested Docs of
  random depth and asserts the union equals the set over `doc.components()`.

---

## 4. Types

- T1 A type is a small class: Python value, JSON Schema fragment, TeX rendering,
  escape/parse, doc string. Registered in a closed vocabulary; additions arrive with
  property tests.
- T2 Shipping types: `Text`, `Markup` (tiny subset: emphasis, strong, break, nbsp),
  `Raw`, `Int`, `Bool`, `Length`, `Colour` (`CMYK`/`RGB`/`Gray`/`Spot`),
  `Path[Kind]`, `Enum`, `List[T]`, `Union` (tagged), `Font`, `Snippet`, `PgfStyle`,
  `Cycle[T]`.
- T3 `Text` is escaped on render (`& % $ # _ { } ~ ^ \`). `Raw` is accepted only where
  declared; balanced braces are mandatory; a `]` inside an optional argument is
  auto-wrapped (`[{a]b}]`); every `Raw` is shown in `show`. **`Raw` is a distinct
  class, not an alias for `str`**, so a type checker rejects a plain `str` where `Raw`
  is expected (and the reverse: a `Raw` is never silently re-escaped). Escaping is
  decided by the field's type at the boundary, never by a mutable per-object flag.
- T4 `Length` parses number+unit, supports min/max, formats stably. Unit correctness
  (`pt` = 1/72.27 in, `bp` = 1/72 in) is property-tested.
- T5 `Colour`: no implicit conversion between models. A `Value[Colour]` may declare
  `variants={"screen": …}` — explicit alternative representations of the same name
  set, guarded (every variant defines identical names). Values carry **provenance**
  (`authored | derived | provisional`) and notes; precedence between sources is data.
- T6 Ordered colour sets (`Cycle[Colour]`) carry a policy (`print_ok | screen_only`);
  a screen-only set gaining a print build fails. A package may declare **retired**
  names/literals; generated output, adopted files and optionally the PDF are scanned.
- T7 `Spot`: handle and separation name are distinct; the proof alternative is explicit
  and documented as never the plate.
- T8 `Font`: files by name, roles, **required OpenType features verified against the
  font file**, resolved through the search path (never an absolute path in output).
  Subsetter `must_keep` lists derive from the same declaration.
- T8a **Static glyph coverage.** Because a `Font` is a known file, every `Text`/`Markup`
  value bound for it is checked against the font's character map (fontTools) *before*
  TeX runs; an uncovered codepoint is a violation naming the path, the codepoint and
  the font (`TM-T020`). Unicode input is normalised to NFC first. The compile-time
  `MissingCharacter` diagnostic (C2) remains as the backstop for glyphs reached through
  `Raw` or fallback.
- T9 Role tables: `role → (size, leading, weight, face)`; checks: leading ≥ size,
  monotonic sizes, weight exists in the face.
- T10 Validation is strict: no coercion, unknown fields refused, errors carry the path
  (`cards[3].back.fact[1]`) and a stable code.

---

## 5. Documents

- D1 A Doc is an immutable tree built with the component classes:
  ```python
  CardBack(Name("Golden Retriever"), Fact("Friendly & loyal."), Slot("A soft woof.", label="Sound"))
  ```
  Constructor signatures are the interface, so pyright flags wrong *argument* types and
  unknown keywords before anything runs; child counts and order are checked by
  `validate()` (M4). Composition is plain Python; there is no second builder language.
  Nodes are frozen dataclasses: **structural equality and hashing** come for free, so
  a Doc can be compared, deduplicated, cached, and asked which components it uses
  (`doc.components()`), and snapshots compare trees, not just text. `repr(doc)` is the
  constructor expression that rebuilds it (`CardBack(Name('Golden Retriever'), …)`),
  used in error messages, goldens and debugging. An environment's arguments are keywords
  and its children are positional: `CardBack(Name("Rex"), Fact("a"), Fact("b"), title="T")`;
  the class-level `children` is the grammar, the instance's `.content` the children.
  `texmodel render module:attr` writes a document (a `str`, or a function returning one) to a file.
- D1a **The document root.** `Package.document(*body, settings=[FactGap(Length("3mm"))],
  options=["a4paper"])` renders a complete `.tex` (pure, deterministic, no I/O) and
  raises every violation at once. Values are set with instances of the `Value` class,
  type-checked against the declared type; class options are validated, since they are
  TeX. `settings=` is the one way to set a `Value` for the whole document; `Set(…)`
  (D4a) is the one way to set it for a subtree; the class `default` is the fallback.
  The root as a component with its own `children` grammar (preamble slots,
  `\begin{document}` body) is the next step; until then the body is a free sequence of
  nodes and only environments carry a grammar.
- D2 `doc.validate()`, `doc.render()` (str, pure, deterministic, no I/O),
  `doc.to_dict()`, `Doc.from_dict()` (migrates then validates), `doc.plan()` (every
  output line with provenance: model | body:line | user value).
- D3 Preamble and slot order are declared by the package; entries are placed by slot.
- D4 **Variants** (e.g. print/preview) set package options/toggles declaratively; no
  string edits.
- D4a **Scoped overrides** (the set-rule idea): a `Set(FactGap("4mm"), …children)` node
  overrides a `Value` for its subtree only, rendered inside a TeX group
  (`\begingroup … \endgroup`) so the override ends where the scope ends. A `Value`
  opts in with `scoped=True`; setting a non-scoped `Value` inside a Doc is a violation
  naming the rule. Only values with defaults can be overridden, never required
  arguments. Scopes nest; inner wins.
- D5 **Rules** are pure functions over the tree returning `Violation(code, path,
  message, hint, severity)`; built-ins: count, order, requires, excludes, placement,
  unique, reference-resolves, length bounds, forbidden type; custom via `@rule`.
  Codes are stable (`TM-C012`) and never reused; warnings can be promoted by policy.
- D6 **Single-sourced content**: a `Snippet` type composes named text from data atoms
  and variants into one macro per variant; the same object yields `text()` for other
  renderers (v1 targets: `tex`, `text`); a test asserts targets agree.

---

## 6. Generation

- G1 `Package.render()` emits a `.sty`/`.cls` of declarations only, deterministic (no
  timestamps or hashes), with a header (generated, model version, how to regenerate)
  and a provenance comment per hunk. **Layout is part of the output contract**: each
  component may declare `begin_paragraph` / `end_paragraph` / `separate_paragraph`
  hints, and `render()` applies fixed blank-line and indentation rules, so generated
  TeX stays readable and goldens diff line-by-line cleanly. Key-value option lists
  render in **declared order**, never dict or set order, so a Python or library upgrade
  cannot reorder `[clip,width=50,trim=…]` and churn every golden.
- G2 **Family check**: the whole family is rendered together and every public control
  sequence used must be declared somewhere in it; every internal used must be defined.
- G3 Known engine traps are encoded as lints with the failure they prevent:
  `\ProvidesPackage/Class` date field linted by **grammar** (`YYYY/MM/DD [vX.Y]
  description`; a bare dotted version in the date slot is an error), `\input@path`
  before `\usepackage` and `\graphicspath` after, fonts resolved by the font loader,
  missing-glyph-is-only-a-warning.
- G4 **Version binding**: a package version may be bound to an external source; the
  framework emits the version macro and provides line from it and refuses mismatch.
- G5 `install` (into a TeX tree; states what it omits) and `bundle` (self-contained,
  **proven** by building with the search environment unset) are distinct.
- G6 `check` regenerates every committed generated artefact, compares byte-for-byte,
  reports stale / missing / orphaned files and verifies the version stamp.
- G7 **Output stability policy.** Generated files record the framework version in
  their header. A patch release never changes the generated output of any input; a
  minor release may, and its changelog has an "output change" entry; `check` reports
  "generated with texmodel X, current is Y: run `build`" instead of a silent diff. The
  framework's own canary packages (the two reference packages of A1) carry goldens
  that gate any output change in a framework PR, and such a PR must be labelled and
  reviewed as an output change.

---

## 7. Compile and measure

- C1 `compile(...) -> CompileResult`: pdf path or none, passes, typed diagnostics,
  pages, log path, timings, engine and package versions, whether it ran in the
  reference image, and probes (C5a).
- C1a **Convergence diagnostics.** The pass limit is explicit (default 5, per-target
  override). When it is reached with `latexmk` still requesting a rerun, the result
  carries `TM-X030 did not converge in N passes` listing the `.aux`/label entries that
  changed between the last two passes (a diff of the two `.aux` snapshots), instead of
  a bare "rerun needed" warning. A document that never converges is a defect in a body
  or a document, and the entries named are where to look.
- C2 Diagnostics are typed and parsed per engine by a pluggable parser:
  `UndefinedControlSequence`, `MissingCharacter(font, codepoint)`, `OverfullBox`,
  `MissingFile`, `PackageError`, `RerunNeeded`, `DocumentRefusal`, `Measurement`.
  Missing glyph and font substitution are errors by default.
- C3 The compile driver is the **only** code that sets search-path environment and
  spawns processes. Argv lists only; shell-escape off unless the package declares it;
  no network.
- C4 **Ordered asset roots** with a shadowing report: when a name exists in two roots
  the resolver says which wins and why; ambiguous names warn.
- C5 **Measured constraints**: a package may declare a `Measure` (a body that records a
  quantity in a machine-readable log line, plus a rule). Results surface as a typed
  diagnostic *naming the offending item*, never a bare non-zero exit. A valid spec can
  still fail to compile; static validation is necessary, not sufficient.
- C5a **Probes** (the `typst query` idea): any body can emit a named, typed value during
  compilation (`\texmodelProbe{name}{value}`, written by LuaTeX to a sidecar JSON next
  to the PDF, keyed by the originating item's path in the Doc). `result.probes` and
  `texmodel make --query NAME` return them as data: box heights, item counts, the page
  a label lands on, remaining room. Tests assert layout facts without parsing the PDF
  (`assert result.probe("fact.height") < Length("12mm")`). `Measure` (C5) is a probe
  plus a limit rule; a probe may exist without any limit. Probes are declared on the
  component (name, type, unit) so the schema and docs list them.
- C6 **Reproducible mode** is explicit (`SOURCE_DATE_EPOCH` pinned; build twice →
  identical PDF bytes); wall-clock mode otherwise.
- C7 **Out-of-tree builds**: intermediates never share a directory with sources;
  `clean` exists and uses `latexmk -c` (`-C` with `--all`), falling back to deleting
  the known intermediate extensions if `latexmk` cannot run.
- C8 **Reference container**: the `releaseart/*` images (source repo
  `release-art/proofpress`), consumed rather than built here. Two flavours observed
  locally on 2026-10-21 (arm64): `releaseart/lualatex` 0.2.0 (TeX Live 2025, LuaHBTeX
  1.22.0, ~750 MB, no Python, no Ghostscript) and `releaseart/lualatex-python` 0.3.2
  (same TeX Live, Python 3.15.0, Ghostscript, veraPDF, ~1.26 GB, AGPL-3.0-or-later
  licence label). Neither has `latexmk`, `pdm`, `uv`, `qpdf` or `pdftoppm`.
  - The compile suite and verifier extras run in `lualatex-python` (it already has the
    verifier tools V4/V5 need); plain `lualatex` is enough for `make --to pdf` in
    downstream projects that bring no Python.
  - **`latexmk` is added to both images** (Perl 5.40 is already present); the install
    route is in the next bullet. The driver uses `latexmk` as the single pass strategy
    (reruns, bibtex/biber, indexes, glossaries); it launches it with
    `-interaction=nonstopmode -file-line-error`, an out-of-tree `-outdir` (C7), and
    reads the final `.log` and `.fdb_latexmk` itself for typed diagnostics and the
    pass count. No second rerun implementation. `doctor` fails clearly if `latexmk`
    is missing, and reports its version; `CompileResult` records that version too.
  - Install route (confirmed 2026-10-21 against `/Users/ilo/Devel/Release.art/proofpress`,
    which builds and releases the images): `latexmk` is a TeX Live package, absent from
    both images (`tlmgr info latexmk` says not installed). Add `latexmk` to
    `docker/texlive-packages.txt` there; the build already installs that list from the
    frozen 2025 `tlnet-final` mirror, so no apt route and no second TeX tree. Perl is
    already installed for tlmgr. Add a `command -v latexmk` check to `bin/docker/smoke.sh`.
    texmodel does not build images; this is a change in the proofpress repo, then a
    released tag that texmodel pins.
  - The image is `releaseart/lualatex-python:latest`, not pinned (decided 2026-10-21, reversing
    the earlier pin-by-version rule): texmodel follows the images, and proofpress is the same
    owner's project. Reproducibility comes from recording, not pinning: every `CompileResult`
    carries the image tag, its image id and its `org.opencontainers.image.revision` label,
    and the compile cache key includes the image id, so a new `latest` is a cache miss and
    never serves stale output. Goldens re-bless when the image moves. `[tool.texmodel] image`
    can still name a version for a project that wants one.
  - `doctor` verifies the image by running a probe (engine, `kpsewhich` of required
    packages, tool presence) and reports capability gaps (e.g. "no verapdf: PDF/A
    checks unavailable") rather than assuming.
  - Findings from building A1: with the image's read-only root, `HOME=/tmp` is a tmpfs, so
    luaotfload rebuilt its font database on every run; the driver mounts a persistent cache
    (`TEXMFVAR`/`TEXMFCACHE`), one directory per image digest. `openin_any=p` (paranoid
    reads) breaks luaotfload, so reads use `r` (restricted) and only `openout_any=p` is
    paranoid: the read boundary is the container's mounts, not TeX's settings. latexmk
    reports non-convergence on stderr. The pass count is the highest `Run number N`.
  - Open: font set and ICC profiles in the images are unconfirmed (the image has ~100
    fonts, no system ICC directory); the framework ships its own open-licence test
    fonts and ICC profile as assets rather than relying on the image's.
  - Licence: texmodel is MIT (decided 2026-10-21). Only `lualatex-python` and `full`
    carry AGPL (they redistribute Ghostscript); `releaseart/lualatex` is LPPL/GPL only.
    texmodel runs the image as a separate process and ships none of it, so its own
    licence is unaffected; confirm that reading before the framework is distributed.
- C9 **Asset licence classes** (`open | embed-only | no-redistribute | no-service`,
  fixed enum): `bundle` refuses `no-redistribute`; a compile context
  (`internal | service`) refuses `no-service` assets.
- C10 **Build targets are data**: declared list with engine, variant and verifier
  profile; reruns until stable (pass limit), parallelism, one summary.
- C11 **Source maps.** `render()` writes a sidecar map (`.texmodel/<doc>.map.json`)
  from every generated `.tex` line to the originating Doc path and, for body lines, to
  `body-file:line`. The compile driver runs with `-file-line-error` and translates
  log locations through the map, so a diagnostic reads `cards[13].back.fact[2]` and
  `fact.tex:1`, not `dogs.tex:482`. A diagnostic that cannot be mapped says so and
  keeps the raw location.
- C12 **Build cache.** A compile is cached under `.texmodel/cache/` keyed on a hash of
  the rendered `.tex`, every package file, every asset, the image digest, engine
  arguments and (in reproducible mode) the pinned epoch. A hit returns the stored
  `CompileResult` (diagnostics, probes, PDF) and says it was a hit; `--no-cache`
  bypasses it; the cache directory can be shared in CI. Only complete results are
  stored; a cache entry is never trusted across a changed image digest.

---

## 8. Verification

- V1 **Free tests** derived from declarations, no author code: per-component smoke
  document with sample values drawn from the types; Hypothesis fuzz (`& ] { } %`,
  Unicode, long strings) asserting clean compile; schema ↔ model ↔ `.sty` ↔ docs
  agreement; name round trips; `Doc` ↔ spec round trip; every mutation to invalid
  fails with the expected code.
- V2 **Authored tests**: goldens (via a snapshot library, accept-with-diff flow showing
  provenance), `assert_refuses(code=, path=)`, `assert_compile_fails(kind)` asserting
  the engine's own reason.
- V2a **Test taxonomy** (the `tytanic` idea), four kinds, all runnable from `check`:
  1. *Smoke*: compiles cleanly (the free tests of V1).
  2. *Equivalence*: two Docs, or two renderings, must produce identical output
     (compared as page text positions, or rasterised pages within a tolerance). Proves
     a body refactor, a rename, or an adopted macro against its generated twin is
     invisible without storing anything. `assert_equivalent(a, b)`.
  3. *Reference*: stored per-page renders (or text-position data) per example, with a
     per-test tolerance, restricted to chosen pages, committed beside the example.
     `check --bless` shows the visual diff before updating. Storage policy (git vs
     LFS) is the consumer's.
  4. *Probe*: assertions over C5a values.
  Every example spec can declare which kinds it takes; a missing reference is a
  failure, not a skip.
- V3 **Compile suite** (`pytest -m tex`) runs in the container over generated docs and
  every package's sample set; examples in generated docs are compiled so docs cannot
  rot. Python-side examples in component docstrings are executed too
  (`--doctest-modules` in the TeX-less suite): `render()` output shown in a docstring
  must match what it produces. PyLaTeX's own docstring examples had silently gone
  stale until doctests were switched on (wrong outputs, a reordered option list).
- V4 **Verifier plugins** (extras), API: `Finding(check, severity, message, page)`,
  `Profile`, `FileReport`. Built in: PDF/A (external validator), PDF/X structure
  (boxes, identity, output condition), ink coverage ceiling, small-text black, overprint,
  named separations, fonts embedded/subset/declared, tabular figures.
- V5 **Unconfirmable = failure.** A missing tool, corrupt file or check that cannot run
  fails. Skips exist only as a declared exemption registry (`path → reason`).
- V6 **Behavioural tests for load-bearing settings** (e.g. tabular figures): render a
  sample, assert the property from the PDF. Typographic invariants on components are
  proved by the compile suite on a sample.
- V7 Coverage gate 100% on TeX-less layers; every requirement id has ≥1 test citing
  it, enforced by a check. Mutation self-check of the rule engine.

---

## 9. Schema and introspection

- S1 `texmodel` exports JSON Schema 2020-12 (`$id` URN) and OpenAPI 3.1
  `components.schemas`. Extensions are `x-texmodel-*`: call, arguments, placement,
  order, form, skeleton.
- S2 A schema field exists iff a model field exists; no hand-edited schema.
- S3 `show NAME` gives signature, rules, placement, count, example; `show SPEC` gives
  the annotated plan. `--json` is a complete machine-readable manual.
- S4 Cross-validator conformance: a standard 2020-12 validator and the Python
  validator agree on every example and every generated invalid case, except documented
  rules the schema cannot express (listed).

---

## 10. Public API, errors and extensibility

The user-facing contract. Python's own design principles (the Zen) are the
tie-breaker: one obvious way, explicit over implicit, errors never silent, flat over
nested, readability counts.

- I1 **One import surface.** `from texmodel import …` is the public API (components,
  types, `Package`, `Doc` helpers, errors). Sub-packages with their own surface are
  exactly `texmodel.std`, `texmodel.testkit`, `texmodel.verify`, and the print extra.
  Everything else is underscore-private; `__all__` is explicit; import-linter forbids
  deep imports in examples and docs.
- I2 **Semantic versioning of the framework itself.** Deprecations emit
  `DeprecationWarning` naming the replacement and are removed no earlier than two minor
  releases later. A public-API snapshot (e.g. `griffe`) runs in CI and fails on any
  unreviewed breaking change. Changelog fragments (towncrier) are required per PR.
- I3 **Typing.** `py.typed`; the library is pyright-strict clean; no `Any` in public
  signatures; `Value[T]` is generic so defaults are checked; no `**kwargs`
  pass-through; options are keyword-only; mode switches are enums, not booleans;
  public value objects are frozen with `__repr__`.
- I4 **Naming conventions.** Classes are nouns, functions are verbs, predicates are
  `is_`/`has_`. The verbs mean one thing everywhere: `render` (to TeX text), `validate`
  (rules), `compile` (engine), `verify` (PDF checks), `show` (inspect), `make`
  (pipeline). Data conversion is `to_dict`/`from_dict`/`to_json`/`from_json`.
- I5 **One obvious way**, stated once per question:

| Question | The way |
|---|---|
| declare an interface | a component class (M1) |
| write a body | `body` as a string or method, or a `TemplateRef` to a file (M8) |
| set a value for the whole document | `Document(settings=[…])` (D1a) |
| set a value for a subtree | `Set(…)` (D4a) |
| build a document | constructors (D1) |
| store a document | `to_dict()` ≡ the spec (D2) |
| change an interface | edit the class; `release` classifies (X5) |
| add behaviour | add a type or a rule, never a new kind (M1) |

- I6 **Convention must be inspectable.** Name, prefix, placement, body file and
  namespace are inferred by default; `texmodel show --resolved` prints every inferred
  decision with the rule that made it, and a missing or ambiguous inference is an error,
  never a guess.
- I7 **Docstrings** use one style (Google), and every public symbol's example is
  executed (V3). The reference is generated from them.
- E1 **One error hierarchy.** `TexmodelError` is the base; subclasses are
  `DeclarationError`, `ValidationError`, `CompileError`, `VerifyError`,
  `MigrationError`, `ToolchainError`. Each carries `.code`, `.path` and `.hint`.
- E2 **All problems at once.** `validate()` returns the list of violations; raising
  APIs raise an `ExceptionGroup` of them, so the first problem never hides the rest.
  The CLI prints them all.
- E3 **A failed compile is a result, not an exception.** `CompileResult.ok`,
  `.diagnostics`; `.raise_for_status()` raises `CompileError` carrying them, mirroring
  common HTTP-client practice.
- E4 **`texmodel explain CODE`** prints the rationale, an example and the fix for any
  stable code; the code registry generates both the command and the reference page, and
  a test fails if an emitted code has no entry.
- E5 **No printing from the library.** It uses `logging` (loggers under `texmodel.*`)
  and `warnings`; only the CLI formats output (`human | short | json | github`).
- L1 **Plugins by entry points**: groups `texmodel.types`, `texmodel.verifiers`,
  `texmodel.engines`, `texmodel.rules`, `texmodel.logparsers`, discovered via
  `importlib.metadata`. Each kind has a contract-test suite the plugin must pass
  (shipped in `testkit`). The testkit itself registers as a pytest plugin (`pytest11`)
  providing markers (`tex`) and fixtures.
- L2 Plugin interfaces are part of the public API for I2.

---

## 11. Standard library (`texmodel.std`)

Without common building blocks every real document needs `Raw`, which is the opposite
of the point. Opt-in package, built with the *same public API as user packages*
(dogfooding; no private hooks), shipping its own bodies, goldens and docs.

- B1 v1 contents: `Paragraph`, `Section`/`Subsection` (starred variants, M3a),
  `Itemize`/`Enumerate`/`Description` with `Item`, `Table` (typed columns, header row,
  totals, decimal-aligned numeric columns), `Figure` with `Caption` and
  `Path[Image]`, `Label`/`Ref`, `Footnote`, `Include`, `Emph`/`Strong` via `Markup`,
  `InlineMath`/`Equation` taking a `Raw` body (balanced, flagged in `show`).
- B2 **Cross-reference integrity is static.** Labels are unique per Doc; a `Ref` to an
  unknown label is a violation (`TM-C0xx`), found without TeX.
- B3 Every std component gets the free tests, goldens, probes and docs of any other.
- B4 Parked for later minors: bibliography/citations/glossaries (the driver already
  handles them via `latexmk`), a typed drawing layer over TikZ. Maths is never modelled
  beyond `Raw` (N1).

---

## 12. Security

Specs come from outside (databases, APIs, users); TeX is a programming language with
file access. The framework must be safe to feed untrusted data.

- Z1 **Trust levels.** `Doc.from_dict(data, trust="untrusted")` is the **default**
  (data from outside); `trust="trusted"` is explicit and is the only mode that accepts
  `Raw`. Untrusted mode also: confines every `Path` to declared roots (no `..`, no
  absolute paths, no symlink escape, resolved then checked); enforces configurable
  limits (node count, depth, string length, total size); rejects control characters
  (except newline and tab) and flags bidirectional controls; applies NFC.
- Z2 **Sandboxed compile.** The container runs as non-root, with no network, a
  read-only root filesystem, only the output directory writable and asset roots
  mounted read-only, with CPU, memory and wall-clock limits; shell escape is off and a
  generated hermetic `texmf.cnf` sets paranoid file access (`openin_any`,
  `openout_any`). Whether Lua file access from `\directlua` is contained by these
  settings is **unverified** (and `openin_any=p` is known not to work with luaotfload, see C8): step B2 includes a verification task, and the
  requirement stands as "a `Raw` body cannot read outside the declared roots, and the
  test suite proves it".
- Z3 **Injection corpus.** A shipped corpus of hostile strings (`\input{/etc/passwd}`,
  `\write18`, `\directlua`, `\catcode`, `\openin`, `\csname`, unbalanced braces,
  `%` comment-eating, `\verb`) is pushed through every `Text` and `Markup` field of
  every component by the free tests. Assertions: the rendered `.tex` contains them
  escaped; the compiled PDF contains them as visible text; nothing outside the output
  directory changed.
- Z4 **Supply chain.** Locked dependencies with hashes, `pip-audit` in CI, a minimal
  dependency set (heavy ones are extras), a licence-compatibility check, trusted
  publishing for releases, a `SECURITY.md` with a disclosure route.

---

## 13. Versions and migrations

- X1 A package has a semantic version (`packaging.version`; pre-releases like
  `1.4.0-dev`); a spec records `model_version`.
- X2 **Dev builds write `schema/next/`**; `release` freezes `schema/<version>/` plus
  examples. Frozen directories are never rewritten.
- X3 **Renames are declared on the model**: `field(renamed_from="text")` compiles to a
  pydantic `AliasChoices` for tolerant reading and records `(from → to, old → new)` in
  the release history. The alias can expire after a declared window.
- X4 **Non-mechanical changes** are written once as a `@migration(frm, to)` function
  (a before-validator in effect). Steps apply as a version-ordered chain (the upcaster
  pattern: an old spec is lifted one version at a time and never validated raw).
  A missing step is an error by default; `compatible_by_default` is opt-in per version.
- X5 **Change classification** (major / minor / none) comes from diffing the
  *declaration models* between the last release and the working tree, using Avro-style
  compatibility rules: adding optional or relaxing = backward-compatible; removing,
  renaming without alias, tightening, changing type or arity = breaking. The consumer
  may override per-package. `build` reports the classification once; `release` acts.
- X6 `release`: classify, scaffold the migration, bump, freeze schema+examples, verify
  every earlier release's examples migrate and validate. Exactly one migration head is
  enforced (branching is caught).
- X7 **Property-based migration test**: generate specs from the *old* schema, migrate,
  assert the new validator accepts them (stronger than committed examples alone).
- X8 `stored_specs = False` marks a package with no persisted specs: `release` skips
  migration scaffolding and the old-example check.
- X9 Non-Python validators see only the current schema, so specs are migrated *before*
  validation at every entry point (`make`, `Doc.from_dict`, CLI).
- X10 Later (parked): squashing old migrations when the oldest supported release moves.

---

## 14. Print extra (`texmodel-print`)

Separate distributable; core stays I/O-light. Both reference consumers overlap here.

- P1 **Geometry**: trim, bleed, media, TrimBox/BleedBox, plus a no-bleed full-page
  variant. Typed lengths in mm; derived values computed in Python and asserted equal to
  TeX's in the compile suite; boxes read back from the built PDF.
- P2 **Conformance** object generates `\DocumentMetadata` (language, standards, colour
  profiles) and validates it against document kind and engine; ICC profiles are bundled
  assets with checksums.
- P2a **Standards are a validated combination**, not stacked flags. `Conformance`
  takes a list (PDF version, PDF/A flavour, PDF/X flavour, PDF/UA) checked against an
  explicit compatibility table (e.g. PDF/UA-1 with PDF/A-4, or UA-1 with PDF 2.0, is
  refused with the reason), the document kind and the engine. If accessibility is
  requested, tagging must be present in the output (verifier V4 asserts it); items that
  need human review (document language set early, artefact marking, alt text) appear in
  a generated review checklist, not as an automated pass.
- P2b `make` and `try` accept `--pages 2,3,7-9,11-` for fast partial renders and
  visual checks; thumbnails for docs and templates are `make --to png --pages 1`.
- P3 Spot colours, ink coverage, rich-black and PDF/A/X verifiers (V4) ship here.
- P4 Asset-root ordering conventions (print variant outranks screen variant on an
  ambiguous name) ship as a documented policy preset, not hard-coded.

---

## 15. Daily use

### 15.1 Layout

```
acme-cards/
├── pyproject.toml                [project] metadata + [tool.texmodel] (prefix, engine, image)
├── acme_cards/
│   ├── __init__.py               Package + small components
│   ├── _shared.tex               shared includes
│   ├── fact.tex                  body of Fact (`body = TemplateRef("fact.tex")`)
│   └── card_back/                a component promoted to a folder when it grows
│       ├── __init__.py  body.tex  example.json  golden.tex  test_card_back.py
├── authored/                     adopted hand-written .cls/.sty + surface manifests
├── generated/                    committed, never edited
│   ├── acme-cards.sty
│   ├── schema/next/…  schema/1.4.0/…   (frozen on release)
│   └── docs/reference.md
├── examples/*.json               specs that build real documents
└── .texmodel/                    ignored: build output, logs, PDFs
```

### 15.2 A whole package

```python
from texmodel import Package, Command, Environment, Value, TemplateRef, Text, Length, Colour, CMYK, LuaLaTeX

pkg = Package("acme-cards", prefix="ac", engine=LuaLaTeX)

class Name(Command):
    """The subject's name, set as the title."""
    text: Text

class Fact(Command):
    """One short sentence under the title."""
    text: Text
    body = TemplateRef("fact.tex")     # explicit: a file next to this module; nothing is found by name

class Slot(Command):
    """A labelled paragraph; the label prints as its heading."""
    text: Text
    label: Text | None = None          # optional ⇒ keyword-only; renders [label] first

class CardBack(Environment):
    """The back face of a card."""
    children = [Name, Fact.times(2, 3), Slot.times(3)]

class FactGap(Value[Length]):
    default = Length("2mm")

class Ink(Value[Colour]):
    default = CMYK(0, 0, 0, 0.95)
```
```latex
% fact.tex
\par\noindent{\ac@factfont #text}\par\vspace{\acFactGap}
```

### 15.3 The loop

- U0 **Configuration lives in `pyproject.toml`; there is no second manifest.** Name,
  version (full SemVer), authors, SPDX licence and description come from `[project]`
  (the single source, the `typst.toml` idea without its duplication); texmodel-specific
  settings (`prefix`, `engine`, `image`, build targets, `exclude` globs that keep large
  assets out of `bundle`, trust limits, performance options) sit in `[tool.texmodel]`;
  `[tool.texmodel.template]` (path, entrypoint, thumbnail) marks a starter project.
  `[tool.<other>]` tables belong to other tools. The package directory and declared
  name must agree. `check` validates the
  configuration and `texmodel init --template <path-or-package>` is the smoke test of a
  template: it scaffolds, builds and compiles it. Distribution through a registry is
  out of scope.
- U1 **A small set of commands** (eleven rows; some rows are a pair of subcommands; the
  daily five are `build`, `check`, `make`, `show`, `try`), `--json` everywhere, exit codes `0` ok / `1` violations / `2` usage /
  `3` environment or tool missing:

| Verb | Does | TeX? |
|---|---|---|
| `init` / `doctor` | scaffold; report what this machine can do | no |
| `build` | declarations → `generated/` (`.sty`, schema `next/`, docs) | no |
| `check` | everything CI runs: drift, namespaces, adopted files, examples validate, goldens, old-release migrations; `--tex` adds the compile suite; `--bless` updates goldens after showing the diff | opt |
| `make SPEC --to tex\|pdf\|verified` | validate → render → compile → verify, stopping where asked | opt |
| `show NAME\|SPEC` | signature/rules/example, or provenance-annotated plan | no |
| `try Fact "text"` | render one call to a cropped image; `--watch` | yes |
| `change` / `release` | classify a change, scaffold its migration; cut a version | no |
| `adopt FILE` | check a hand-written file against its manifest | no |
| `bundle` / `install` | self-contained export; install into a TeX tree | yes |
| `refactor rename\|promote\|fmt` | libcst-based rename of a component (class, its `TemplateRef` targets, examples, goldens, rename record), promote to a folder, promote inline bodies to files | no |
| `clean` | remove build output (`latexmk -c`, `--all` for `-C`) | no |

- U2 **Errors name a path, a code and the fix**, human first, JSON available:
  ```
  TM-C011  examples/dogs.json: cards[2].back.fact: 4 items, at most 3
           rule: CardBack.children (acme_cards/__init__.py:31)
  error    TM-X021  overset: card 14 "Great Spotted Woodpecker"
           region Fact (3 items) overflows the card by 4.2 mm
           source examples/dogs.json:cards[13].back.fact
  ```
- U3 A generated file edited by hand fails `check` with the provenance of the line
  and the fix (`texmodel build`).

### 15.4 What a diff looks like

Adding `Fact`:

```
 acme_cards/__init__.py                    (+6)  class Fact(Command) …        read
 acme_cards/fact.tex                       (+1)  the body                     read
 generated/acme-cards.sty                  (+3)  provenance-annotated         skim
 generated/schema/next/deck.schema.json    (+9)                                skim
 generated/docs/reference.md               (+5)                                skim
```

Every generated hunk starts with `from <Class> (body: <file>)`. No version directory
churn, no migration file until `release`. A breaking change prints once at `build`:
`note Fact: argument label added (MINOR vs 1.3.0).`

### 15.5 Editing, in short

- Body only → fragment + one generated hunk; schema untouched (the "internals only" signal).
- Interface change → `build` classifies; arity or removal needs `release` to scaffold the
  migration; renames use `renamed_from`.
- `texmodel refactor rename` (via libcst) rewrites class, `TemplateRef` targets, examples,
  goldens and adds the rename record. `texmodel refactor promote Fact` moves a component
  into a folder.

### 15.6 CI

```
texmodel check               # drift, namespaces, adopted files, examples, goldens, migrations
ruff / pyright               # style and types
pytest                       # TeX-less layers, coverage gate, free tests
texmodel check --tex         # compile suite + verifiers in the reference container
```

---

## 16. Engineering standards and documentation

- W1 **Gates**, one entry point (`check`): ruff, pyright strict, pytest with 100%
  coverage on the TeX-less layers, import-linter contracts, mutation testing
  (`mutmut` or equivalent) on `core`, `types` and `rules` with a score floor, pre-commit
  hooks mirroring CI.
- W2 **Performance budgets**, enforced with `pytest-benchmark` and a regression gate
  (fail on >20% slowdown): validating a 10,000-node Doc under 1 s; rendering it under
  1 s; building a 100-component package under 2 s; schema export for it under 1 s;
  `texmodel --help` under 300 ms (lazy imports). Budgets are revisited, not silently
  loosened.
- W3 **Platforms.** Python 3.15 only (decided 2026-10-21, as the reference images ship 3.15); TeX-less layers on Linux and
  macOS (Windows best-effort); compiling is via the reference container on any host.
- W4 **Documentation (Diataxis).** A tutorial (first package in fifteen minutes), how-to
  guides (add a component; adopt a hand-written class; cut a release; write a verifier
  plugin; sandbox a compile), a generated reference (components, types, error codes,
  CLI), and explanation pages (the ORM mapping, trade-offs, security model). The docs
  build runs in CI with every example executed, is versioned per release, and the two
  reference packages are the examples gallery.
- W5 **Project hygiene.** LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY.md, issue
  and PR templates, CODEOWNERS, a changelog from towncrier fragments, release
  automation.

---

## 17. Dependencies and borrowed patterns

Libraries: `pydantic` v2 (validation boundary, aliases; hidden behind `types`),
`typer`, `hypothesis`, `packaging` (versions), `graphlib` (stdlib; layering, migration
order), `libcst` (rename/promote refactors), a snapshot library (`inline-snapshot` or
`syrupy`; evaluate before building `bless`), `ruff`, `pyright` strict, `pytest`,
`import-linter`. Extras: `pikepdf`/`pymupdf`, `fontTools`, external `veraPDF` and
Ghostscript in the container.

Patterns: Alembic (revision chain, autogenerate by diff, single-head check); event
sourcing upcasters (stepwise lift of stored data); Avro/Protobuf compatibility rules
(classification); Django squashing (parked); SQLAlchemy (declarative models, dialects,
reflection, unit of work).

Borrowed from Typst (ideas only): probes from `typst query` (C5a); scoped overrides
from set rules (D4a); the compile-only / ephemeral / reference test split from
`tytanic` (V2a); PDF standards as validated combinations with a tagging requirement,
and `--pages` (P2a, P2b); the manifest and template smoke test from `typst.toml`
(U0); bounded layout passes with a reported non-convergence (C1a). Not borrowed: show
rules (rewriting elements at render time), `context` expressions, an embedded scripting
language. Unverified in the review: how Typst reports argument-type errors, and
`tytanic`'s on-disk reference layout.

Borrowed from PyLaTeX (MIT; ideas only, no code): per-component package requirements
collected into the preamble (M14), a distinct unescaped-text marker type (T3),
structural node equality and constructor `repr` (D1), starred variants (M3a),
paragraph/layout hints (G1), `latexmk -c` cleaning (C7). Deliberately not borrowed:
stringly-typed arguments, escaping by mutable flag, global mutable config, raw
subprocess exceptions, package propagation by tree mutation.

Rejected: SQL/Django migration libraries; `jsonpatch`/`glom` for migration steps
(plain Python is clearer); Jinja/`string.Template`/`$name` hole syntaxes; 3.14
template strings for bodies (TeX braces fight interpolation).

---

## 18. Package structure

Two distributions in one repository, released in lockstep (decided 2026-10-21): `texmodel` (`src/`), the rendering
core, which never spawns a process; and `texmodel-build` (`harness/`, import `texmodel_build`), the optional compile and
verify side (§7, §8), configured in `[tool.texmodel-build]`. Consumers that already pin a toolchain in an image (as the
owner's do) need only the first. The compile cache, container sandbox flags and `bundle.prove` described in §7 and §12 were
built and then removed: the images carry reproducibility, and the container is the environment, not a sandbox.

Convention (decided 2026-10-21, as pydantic and proof-pdf do): public API is the top-level
modules of `texmodel/`; private implementation lives in `texmodel/_internal/`. A test lists
the public modules, so a new top-level module is a deliberate API decision (I1). The tree
below is the target shape; as built so far, `compiler`, `engines`, `roots`, `targets`,
`result`, `diagnostics`, `config`, `errors`, `cli` are public and `logparse`, `converge`,
`env`, `cache`, `spawn` are `_internal`.

```
texmodel/
  core/      components, Package, namespace, registry, placement       (no I/O)
  types/     Text, Markup, Raw, Length, Colour, Path, Font, …          (no I/O)
  rules/     Rule, Violation, built-ins                                (no I/O)
  render/    package + doc rendering, bodies, lints, family check
  engine/    profiles, escape tables, compile driver, log parsers      (only spawner)
  schema/    JSON Schema / OpenAPI export, show
  migrate/   chain, classification, release, property test helpers
  adopt/     manifest + scanner (conformance mode)
  testkit/   free tests, snapshots, assert_refuses, tex fixtures
  verify/    verifier plugin API (+ built-ins as extras)
  std/       standard component library (opt-in, built on the public API)
  security/  trust levels, limits, sandbox policy, injection corpus
  cache/     content-addressed compile cache
  errors.py  the single error hierarchy
  cli.py
texmodel-print/   geometry, conformance, print verifiers, policy presets
```

An import-linter contract keeps `core/types/rules` free of I/O; `engine` is the only
module that spawns processes. Python 3.15 (W3).

---

## 19. Phasing: three stages with gates

The plumbing is the proven duplication; the model layer is the speculative part. So
the work is staged and each gate is a real go/no-go, not a formality.

### Stage A: plumbing (valuable on its own)

| Step | Deliverable | Covers | Exit test |
|---|---|---|---|
| A0 | repo, standards, API skeleton, errors, logging, `[tool.texmodel]`, CLI shell, `doctor` | I, E, W, U0 | gates green; `doctor` probes the image. **Done 2026-10-21** except the image probe, which moves to A1 (only `engine` may spawn processes) |
| A1 | engine: `latexmk` driver, container integration, typed diagnostics, hermetic env, reproducible mode, build cache, `clean` | C1-C4, C6-C8, C10, C12 | compile suite green in CI; two builds byte-identical. **Built 2026-10-21**: suite passes locally in a derived image (`releaseart/lualatex-python` + `tlmgr install latexmk`) with byte-identical reproducible builds; the CI job is `continue-on-error` until proofpress releases an image with `latexmk` (change prepared, uncommitted there) |
| A2 | verifier plugin API + built-ins, drift `check`, `bundle`/`install`, entry-point plugins | V4, V5, G5, G6, L1 | unconfirmable ⇒ fail demonstrated |

**Gate A.** Both consumers delete their own driver/install/verify code in favour of
this stage with existing tests passing (acceptance A5). If that is not true, stop and
fix before building anything on top.

### Stage B: model proof (on one consumer's cards)

| Step | Deliverable | Covers | Exit test |
|---|---|---|---|
| B0 | types, components, `children`, naming, rules, static glyph check; no TeX | M, T, D5, E2 | property tests, 100% coverage. **Partly built 2026-10-22**: `Text` (escaped), `Raw`, `Length`, `Colour`, `Bool`; `Command`, `Environment`, `Value[T]`; `children` grammar and `validate()` returning every violation; rules as a pluggable layer, `Markup`, `Int`, `Enum`, `List`, glyph check not yet. Gate B (2026-10-22) found `Enum`/`List`, text-valued settings and a grammar for "anywhere" items missing for the first consumer |
| B1 | bodies, package render, family check, lints, `build`, output-stability header | M8, M14, G1-G4, G7 | sample `.sty` byte-stable; hand edit fails `check`. **Built 2026-10-22** (also `texmodel render`, and `tests/examples/` goldens that the compile suite builds). Adopted packages (M9, minimal): `adopted=True`, `Package.check_interface`, `texmodel check` with `sources` (2026-10-22) |
| B2 | Doc trees, document root, spec round trip, `show`/`plan`, source maps, trust levels, injection corpus, **sandbox verification task** | D1-D4a, C11, Z1-Z3 | hostile corpus passes; map resolves a real diagnostic. **Partly built 2026-10-22**: Doc trees (constructor trees, `validate()`), the document root with `settings=`, `options=` and three preamble slots (`PreambleSlots`, D3, minimal); `Package.plan()` with per-line paths, `path_of` and a JSON baseline built (2026-10-22); spec round trip, `show`, trust levels, corpus, sandbox task and mapping a diagnostic automatically not built |
| B3 | schema/OpenAPI export, cross-validator test, free tests, probes and `Measure` | S, V1, C5, C5a | S4 passes; overset ⇒ diagnostic naming the item. **Not built** (2026-10-22): schema export, `Measure`, probes. The harness types a package's own warning (`PackageWarning`, `TM-X019`), which is how the first consumer's brand package reports a card that does not fit |

**Gate B (go/no-go).** On the first consumer: the generator's regex drift code is
deleted; at least three real past defects (interface drift, an escaping bug, an
over-set card) are shown to be caught by the new checks; adding a component takes an
author under ten minutes. If not met, stop at the plumbing plus a smaller model layer.

**Gate B was run on 2026-10-22 against a real private card deck (its snapshot is not kept in this repo; `tests/consumers/card_deck/` is a synthetic stand-in with the same shape); the evidence and the recommendation are in
`docs/briefs/gate-b-report.md`.**

### Stage C: only if Gate B passes

| Step | Deliverable | Covers |
|---|---|---|
| C0 | releases and migrations | X1-X10 |
| C1 | adoption of hand-written TeX | M9, M10 |
| C2 | `texmodel.std` | B1-B4 |
| C3 | equivalence and reference tests | V2a |
| C4 | `texmodel-print` | P1-P4, T5-T7, C9 |
| C5 | docs (Diataxis), performance budgets, 1.0 | W2, W4, W5, A1-A10 |

---

## 20. Acceptance

- A1 Two **reference packages** with different shapes — a grammar-driven card deck, and
  a stationery set (bleeding piece, A4 report, slide deck, dual-representation palette,
  embed-only font via an open-licence stand-in) — build from the public API and pass
  their verifier profiles in the reference container.
- A2 Every requirement id has a test citing it; a check fails otherwise.
- A3 Lint, types, TeX-less tests (100% coverage) and the compile suite all pass in CI;
  the compile suite is a required gate.
- A4 Generated `.tex`/`.sty` are byte-identical across runs and machines; reproducible
  PDFs rebuild byte-identically.
- A5 Each consumer's driver/install/verify code can be deleted in favour of the
  framework with its existing tests passing.
- A6 A hand-written class passes conformance mode with only a manifest added.
- A7 A rename and a non-mechanical change both ship through `release` with working
  migrations, and old examples migrate and validate.

- A8 The hostile-string corpus (Z3) passes for every component in both reference
  packages, and the sandbox verification (Z2) is recorded as a passing test or as a
  documented limitation with the mitigation.
- A9 The public-API snapshot, changelog fragments and deprecation policy (I2) are
  enforced in CI; the performance budgets (W2) are enforced by the benchmark gate.
- A10 The docs build executes every example, and a newcomer can follow the tutorial to
  a compiled PDF in fifteen minutes (timed once by someone who has not seen the code).

---

## 21. Decisions log

| Decision | Status |
|---|---|
| Three components + types as the only extension point | decided |
| Python signatures are the interface; bodies are explicit TeX (string, method or `TemplateRef`), never found by name | decided 2026-10-22 |
| A body method is read once at class definition and cannot use `self` | decided 2026-10-22 |
| Environment: fields are keyword arguments, children positional; `children` is the grammar, `.content` the instance's children | decided 2026-10-22 |
| `Package.document(...)` renders a `.tex`; values are set by `Value` instances in `settings=` | decided 2026-10-22 |
| `texmodel render module:attr` writes a document to a file | decided 2026-10-22 |
| Hole syntax `#name`; internals free but must resolve | decided |
| Documents are constructor trees (not `with` builders) | decided |
| `children = [Fact.times(2, 3)]` multiplicity syntax (`times([from,] to)` with `to=None` for no limit, plus `times.any()` and `times.at_least_one()`; not operator overloading) | decided 2026-10-22 |
| An adopted (declared-only) package is a flag on the package, `Package(..., adopted=True)`: no bodies, no `.sty`, `texmodel check` compares the declarations with `[tool.texmodel] sources` (alternatives: a per-component marker; a separate class; a manifest file, M9) | decided 2026-10-22 |
| The interface check reads `\newcommand`, `\providecommand` and `\newenvironment` and compares the argument count and whether the first is optional; a name defined another way is missing (`TM-C010`, `TM-C011`) | decided 2026-10-22 |
| Document preamble: `PreambleSlots(before_class, before_package, after_package)`, each a tuple of `Raw`, passed to `Package.document(preamble=)`; public names used there are linted (`TM-M015`) (alternatives: free strings; slots declared by the package; a root component with its own grammar) | decided 2026-10-22, minimal D3 |
| A deck-level text setting (`\renewcommand{\bbDeckName}{...}`) is a declared, argument-less Command until `Value[Text]` exists | decided 2026-10-22, provisional |
| The harness types any package warning (`PackageWarning`, `TM-X019`); a package's "does not fit" message is read by the consumer until `Measure` exists | decided 2026-10-22 |
| Consumer evidence lives in a committed snapshot (`tests/consumers/`); the one `consumer` test reads the live deck read-only and is skipped without it | decided 2026-10-22 |
| A source map is a `Plan`: output lines with the path that wrote each; the baseline for hand-edit detection is its JSON, stored beside the committed file | decided 2026-10-22 |
| A text setting is `Value[Text]`: `\newcommand` with an escaped default in a generated `.sty`; `settings=` writes `\renewcommand` after `\usepackage` (before the preamble slot, not in the body); an adopted package may declare only a `Value[Text]`, checked as an argument-less command | decided 2026-10-22 |
| A closed set is a `Choice` enum whose member values are the TeX (`Raw` passes through, `str` is escaped); data names a member by name | decided 2026-10-22 |
| Documents are checked against the model's render, with no baseline file (`[tool.texmodel.documents]`, like `terraform plan`); hand edit and config change are not told apart | decided 2026-10-22 |
| Pydantic v2 is a dependency, used at the data boundary only (`texmodel.spec`: `from_dict`, `to_dict`, `json_schema`); component classes stay stdlib frozen dataclasses; default (lax) coercion; its errors are mapped to `Violation` / `ValidationError` with `TM-C020` and `validate()`-style paths | decided 2026-10-22 |
| Python-only authoring; TOML/YAML frontend | parked, not planned |
| Renames via `renamed_from` → pydantic aliases + release record | decided |
| lualatex only in v1; capabilities explicit | decided |
| Print features in a separate extra | decided |
| Licence classes: fixed small enum | decided |
| `Snippet` targets: `tex` + `text` in v1 | decided |
| Strict colour: no implicit conversion, explicit guarded variants | decided |
| Reference container: the `releaseart/lualatex` and `releaseart/lualatex-python` images, `latest` (not pinned) | decided 2026-10-21 |
| `latexmk` baked into the images and used as the single rerun strategy (no own loop) | decided |
| Project and package name: `texmodel` (alternatives considered: texcontract, typedtex, texspec) | decided |
| API surface, error hierarchy (`ExceptionGroup`), plugins via entry points | decided |
| `texmodel.std` ships in v1 stage C, built on the public API | decided |
| Untrusted is the default trust level for `Doc.from_dict` | decided |
| Config in `pyproject.toml` (`[tool.texmodel]`), no separate manifest | decided |
| Staged phasing with Gate A and Gate B | decided (proposed 2026-10-21) |
| Lua file access from `\directlua` inside the sandbox | open — verify in B2 |
| Mutation testing: mutmut (runs on 3.15, `pdm run mutmut run`); score floor | tool decided 2026-10-21; floor open until `core`/`types`/`rules` exist (first run: 42 of 60 killed, survivors are message strings and hints) |
| Project licence: MIT | decided 2026-10-21 |
| Python 3.15 only | decided 2026-10-21 |
| Image font/ICC content, and the MIT-vs-AGPL-image reading (C8) | open — check in A1 |
| Snapshot library vs own `bless` | open — evaluate in C3 |
| Exact list of built-in rule codes | open — B0 |

---

## 21a. Gate B findings: ideas, gaps, improvements (2026-10-22)

From running Gate B on a real card deck and its hand-written package family (private; `tests/consumers/card_deck/` keeps the
shape with made-up data). Ordered by how much the consumer missed them. Each is a candidate, not a decision.

1. **Typed settings and labels.** `Choice` (the enum field type) is built 2026-10-22; `Value[Text]` too (2026-10-22); open: `List`, and `Value[Raw]`. Today a per-deck text setting is an
   argument-less adopted Command whose value is `Raw` in the preamble, and a slot label is a `Raw` field fed by a consumer enum.
   `Enum` would also give a closed set of labels to validate and to export.
2. **Typed over-set: `Measure` (C5).** A package reports "card X does not fit, needs A, has B" as its own warning; the harness
   types it (`PackageWarning`) but the consumer reads the numbers by regex. Idea: a declared parser per package (message
   shape to named measurements), or a probe convention the package can adopt; verdict per item against a declared bound.
3. **Automatic diagnostic mapping.** Built 2026-10-22: `Compiler.compile(..., plan=)` adds `path` to every diagnostic located in
   the source (C11). Open: a package warning's `input line N` has no file, so one raised inside another file is mislabelled;
   the CLI has no way to pass a plan (it needs the baseline workflow, item 5); diagnostics from `.sty` files get no path.
4. **Grammar escape hatches.** Ordered runs cannot say "this item may appear anywhere, any number of times" (a section
   header) or hold a raw child (a layout `\vspace`). Ideas: an `Anywhere(X)` term; a `Raw` node allowed in a grammar by
   declaration; interleaving of two runs. Without it a model cannot match a generator's layout, only its text.
5. **Documents in the CLI.** Built 2026-10-22 without a baseline file (the model is the reference, as in `terraform plan`):
   `[tool.texmodel.documents]` maps a committed `.tex` to a pointer returning a `Plan`; `texmodel check` names each difference
   by component path. Open: telling a hand edit from a config change needs the old render (a saved plan or git); passing a
   plan pointer to `texmodel-build compile` so diagnostics print paths; `texmodel render` for every configured document at once.
6. **Hand-edit semantics.** The old regex tool separated a hand edit from a config change, matched cards by id, ignored a
   triage tool's marker comment, and produced the config edit that imports a hand edit. Ideas: keyed children (path by id,
   not position), a declared "comment marker to ignore" on the plan comparison, and an `import` hook that maps a path to a
   source field.
7. **Rules layer (D5) and placement (M5).** The package enforces counts itself with its own errors; texmodel duplicates them in
   the grammar. A rule such as a reading-level bound belongs to neither.
8. **Adoption scanner reach.** Reads `\newcommand`, `\providecommand`, `\newenvironment` only: not `\NewDocumentCommand`,
   `\DeclareRobustCommand`, defaults other than the first argument, or `\newcommand*` forms with unusual spacing. Also: names
   the package defines that the model does not declare (present-but-undeclared, M9), and renewals of declared names (M10).
9. **PDF-string safety.** A deck's PDF Info string was cut inside a parenthesis, which silently swallowed the rest of the
   dictionary. Idea: a `PdfString` type that escapes and balances; `Text` is TeX-escaped, not PDF-escaped.
10. **Preamble.** Slots are three tuples of `Raw`. Ideas: typed entries (`PassOption`, `InputPath`, `GraphicsPath`), the
    ordering rules in the plan's G3 as lints (input path before the package, graphics path after), and slots declared by
    the package (D3).
11. **Source maps beyond documents.** A `.sty` render could carry a plan too, so a `Package` diagnostic or a hand edit to a
    generated `.sty` names the component.
12. **Declared-only variants.** If a consumer mixes generated and adopted components in one package, `adopted=True` on the package
    is too coarse; the alternative is a per-component marker. Revisit with the second consumer.
13. **Consumer policies in the library?** Title case, apostrophe normalisation and PDF-subject cutting were consumer code. They
    are probably policy, but a `Text` variant with a declared normaliser would remove the converter's busiest part.
14. **Reference image.** `releaseart/lualatex-python` lacked `enumitem`, `hyphenat`, `anyfontsize`, `pdfrender` and `tikzfill`
    (found by compiling a real brand package; `tlmgr install` adds them). Idea: a documented "full" tag, or a doctor check that
    names missing packages for a given `.sty`. PDF/X-4 and PDF/A-2b output was never compiled in the test; an ICC profile
    has to be supplied at test time.
15. **Spec round trip** (`to_dict` / `from_dict`): first version built 2026-10-22 as `texmodel.spec` on pydantic (data shape: a child
    names its component with `"type"`; environments take `content`; error paths as `validate()`). Open: `Doc` with migrations
    (X), `renamed_from` aliases, data-to-component mapping (item 16), `json_schema` for a whole package,
    and walking pydantic's field info for docs and constraints instead of our own `_arguments` (not needed for TeX signatures).
16. **Data-driven rendering (the workflow the first consumer wants).** Run `texmodel` on a card data file (TOML, or Python
    dicts/structs) against the project's templates and get the documents, with no hand-written converter:
    `texmodel render --data cards.toml <pointer>`. Needs: `Doc.from_dict()` / `to_dict()` (spec round trip, D2, with
    validation and a migration hook); a declared mapping from data fields to components, kept next to the components (joins such
    as three "spot" lines into one slot, slot order, deck policies like title case); an `Enum` field type for labels; and a
    template directory argument or a `[tool.texmodel] templates` key, so bodies (`TemplateRef`) and adopted `sources` are found
    from configuration, not from the pointer. Today the cards-to-nodes step is consumer Python and a TOML frontend is parked
    (§21), so this reopens that decision. Decided 2026-10-22: log it, and make the existing pipeline operational first.
17. **Typed references inside bodies, with automatic requires.** Built 2026-10-22 (`Hole`, `Ref`, `call` / `open` / `close`,
    `Package.depends_on`, `\RequirePackage` from references, `TM-P007` cycles). The target must be registered before the body that
    calls it (a body is read when its class is defined, so a forward reference cannot exist). Open: conditions and loops as
    pieces (item 19), stubbing (item 20). Design: A body is text chunks plus references to declared components,
    not an AST (N1 holds): `Fact.call(Hole("text"))` stands for `\acFact{#text}`, `Box.begin(...)` / `Box.end` for an
    environment. The reference carries the class, so arity and the optional argument are checked when the body is defined and a
    rename cannot leave a stale string. A reference to a component of another package records that package as a dependency
    and the generated `.sty` gets `\RequirePackage{other}`, sorted and computed from the references (as M14), also for an
    adopted package; a cycle between packages is refused. Plain strings with `#name` stay valid. The family check (G2) then
    covers cross-package names without scanning. Needs: a body representation (string, or sequence of str and references),
    package dependencies on `Package`, and an order for `\RequirePackage` lines.
18. **Whitespace policy on a body token (the `%` at line ends).** Built 2026-10-22 (`texmodel.body`: `TexRaw`, `Whitespace`, body
    sequences/generators, `Package(whitespace=)`); `EXPL3` mode and the pieces-with-calls part (items 17, 19) are open. Design: A newline in a macro body is a space token, so authors end
    lines with `%`. Proposed: a body piece `TexRaw(body, whitespace=Whitespace.TRIM)` (distinct from `Raw`, a field value
    without holes): `body` is `textwrap.dedent`ed and stripped of leading and trailing blank lines at construction, and
    `Whitespace` (`@enum.unique`: `KEEP`, `TRIM`; later `EXPL3`) says how its line ends are written. `body()` (or any
    generator) returns one `TexRaw` or a sequence of pieces and component calls (items 17, 19); each piece carries its own
    policy. `TRIM` appends `%` to every line of the piece, including the last, except a line that already ends with `%`, a
    comment line, or a blank line (a paragraph break); explicit spaces (`\ `, `~`) are untouched. `KEEP` writes the lines as
    given, so a plain string or `TemplateRef` body (which means `KEEP`) renders exactly as today. Pieces are joined by newlines in
    the output. `TemplateRef("f.tex", whitespace=...)` takes the same policy. The generated `.sty` still carries the `%`.
    Lint: `\verb`-like content in a `TRIM` piece. Later mode: expl3 (`\ExplSyntaxOn`, M8 `syntax = expl3`), where whitespace is
    ignored and no `%` is needed. The default is `KEEP`, explicit per piece, so no existing output changes.
19. **Generated bodies that are well-formed by construction.** Beside hand-written TeX bodies (strings, `TemplateRef`), a
    body may be built from a small constructive vocabulary: text (escaped), `Raw`, a group (balanced by construction), a
    control sequence (name validated), a call to a declared component (arity and optional argument checked, item 17) and a
    hole. It is an emitter, not a parser or expander: texmodel never reads TeX it did not write (N1 reworded to say so).
    Conditions and loops stay in Python (one branch per `Choice` member is a loop emitting pieces). Adopted (hand-written)
    packages keep declaring interfaces only.
20. **Unit tests of generated code with stubbed dependencies.** The component references of a body (items 17, 19) say what to
    stub. `pkg.test_document(node, stub=[Fact])` builds a `.tex` with the real definition of the component under test, a
    stub per dependency that logs its call and arguments instead of typesetting, and the node. Stubs write
    `texmodel:probe:<name>=<value>` lines (`\typeout` or `texio.write_nl`), which the harness already parses into typed
    `Measurement` diagnostics (C5a), so a test asserts calls and arguments, not a PDF. A fast tier needs no TeX: walk the
    structured pieces in Python with stubbed calls, to test what the generator decided. The LuaLaTeX tier checks the real macros
    expand as expected; it does not prove layout. Order: item 17, the emitter, a stub runner in `texmodel-build`'s `testkit`.
21. **`Comment` node.** Every line it renders is prefixed `%`; a subclass declares fields and a `#name` template (an audit block
    above a card). Usable as a body piece and as a document node; transparent to the grammar; named in the plan; skippable in
    `Plan.edits`. Brief: `docs/briefs/roadmap.md` A4.
22. **Gate B itself.** The ten-minute criterion needs a first-time author, timed. The "three real past defects" criterion needs
    a consumer whose history records an escaping bug and an over-set card; the first consumer recorded only interface drift.

The ideas above are arranged into batches an agent can run unattended in `docs/briefs/roadmap.md`.

## 22. Risks

- **Scope creep toward a TeX interpreter** (N1). Mitigation: interfaces only; dynamic
  behaviour is bodies plus measured constraints.
- **Body lints false positives/negatives.** Mitigation: conservative lints, each citing
  the real failure it prevents; the compile suite is the arbiter.
- **Adoption scanning is heuristic** (catcodes, `\csname`). Mitigation: scan modelled
  declaration forms only; report the rest; manifest authoritative.
- **Two consumers pull policy in opposite directions.** Mitigation: policy is data on
  the package; the core has no colour or naming opinion beyond "no implicit conversion".
- **Toolchain variance / image upkeep.** Mitigation: reference container is the source
  of truth; versions and image id recorded in every result; goldens re-bless when `latest` moves.
- **Layout bugs that compile.** Mitigation: goldens, PDF verifiers, `try`; typed holes
  and free tests close injection and arity classes, not taste.
- **Schema cannot express every rule.** Mitigation: a documented residue list, covered by
  the conformance test.
- **Solo-maintainer scope.** The plan is large for one person. Mitigation: the staged
  phasing with two gates; stage A is useful alone.
- **Public API churn before 1.0.** Mitigation: the API snapshot and deprecation policy
  (I2) apply from the first release, even at 0.x.
- **`texmodel.std` growing without bound.** Mitigation: v1 list is closed (B1);
  additions need a user-facing case and the same tests and docs.
- **Sandbox gaps.** Mitigation: Z2 is a verification task with a test, not an assumption;
  until proven, untrusted specs never include `Raw` (Z1).
- **Pydantic coupling.** Mitigation: it is hidden behind `types`; public signatures do
  not expose its classes.
