# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Documents in the CLI (B1): `texmodel render` with no pointer writes every `[tool.texmodel.documents]` entry to its path;
  `texmodel-build compile --plan <pointer>` and a target's `plan = "<pointer>"` give diagnostics the component path.
  `texmodel.pointer` (`load_package`, `load_document`, `load_plan`) is public so the harness reads the same pointers.
- `Comment` (§21a 21): `texmodel.body.Comment(text)` prefixes every line with `% `; a subclass declares fields and a `#name`
  `template` (`TM-M028` for a hole that is not a field or a field never used). It is a body piece and a document node
  that is transparent to the grammar and has a plan path; `Plan.edits(text, ignore_comments=True)`; `from_dict` and
  `json_schema` take `comments=[...]`.
- Rendering core (plan B): `texmodel.components` (`Command`, `Environment`, `Value[T]`, `TemplateRef`), `texmodel.package.Package`
  and `texmodel.types`. A component is a class; its fields are its arguments (an optional field is keyword-only and TeX's
  one optional argument) and its docstring is its documentation. `Package.render()` writes a deterministic `.sty` with a
  provenance comment per component. Declarations are refused at class definition with stable `TM-M0xx` codes.
  `texmodel build` and `texmodel check` (`[tool.texmodel] package`, `output`) write and drift-check the generated files.
- Bodies are explicit TeX: a `body` method returning it (or a string attribute), or a `TemplateRef("file.tex")`, resolved
  relative to the module that defines the class. `Environment` has `begin` / `end` in the same way. A method is read once,
  when the class is defined, and cannot use `self`; indentation and surrounding blank lines are removed.
- `Value[Length | Colour | Bool]` renders `\newlength` + `\setlength`, `\definecolor` (`ac-ink`, `ac-brand-red`) or `\newif`.
  `texmodel.types` has `Length`, `CMYK`, `RGB`, `Gray`, `Colour`, `Bool`, `Raw` and `escape`. `needs_packages` is data on the
  component; the `.sty` emits the sorted union as `\RequirePackage` lines (M14). A body naming an undeclared
  `\<prefix>Name` is refused at `render()` / `texmodel check` (`TM-M015`).
- Documents (T3, M4, D1, D1a, D2, E2): `Package.document(*nodes, settings=, options=)` renders a complete `.tex`. `Command` and
  `Environment` instances `render()` and `validate()`. `Text` fields are escaped; `Raw` is a distinct, brace-balanced type
  for TeX that must pass through. An environment's `children = [Name, Fact.times(2, 3), ...]` grammar is checked by
  `validate()`, which returns every `Violation` with a path (`TM-C001`-`C003`, `C006`, `C007`); rendering raises them as an
  `ExceptionGroup`. `repr()` of a node is the constructor expression.
- `texmodel render module:attr [-o out.tex]` writes a document (a `str` from `Package.document()`, or a function returning
  one). An invalid document prints every violation with its code and path and exits 2.
- Adopted packages (M9, minimal): `Package(..., adopted=True)` declares the interface of a hand-written `.sty`. Its components
  have no body, `build` writes nothing, and `texmodel check` (with `[tool.texmodel] sources`) reports a declared name the
  sources do not define (`TM-C010`) or define with another signature (`TM-C011`). A body or a `Value` on an adopted package
  is refused (`TM-M023`, `TM-P005`).
- `Package.document(..., preamble=PreambleSlots(before_class=, before_package=, after_package=))` (D3): `Raw` TeX around
  `\documentclass` and `\usepackage`; public names of the package used there must be declared (`TM-M015`, with a path).
- `texmodel_build`: a package's own warning is a typed `PackageWarning` (`TM-X019`) with its continuation lines joined and its
  input line; an undefined control sequence inside an argument is named from TeX's `<argument>` line.
- Pointers (`[tool.texmodel] package`, `texmodel render`) are `module:object`, `module:namespace.object` or `module:getter()`;
  a trailing `()` calls the getter with no arguments. A malformed pointer is `TM-D020`; a failed import, lookup or call is `TM-D021`.
- `Compiler.compile(source, outdir, plan=)`: with the `Plan` that wrote the source, every diagnostic located in it carries `path`
  (`Card[1]/CardBack[1]/LabelledSlot[3]`); `texmodel-build` prints it in brackets.
- `texmodel.spec` (D2, S; pydantic): `from_dict(cls, data)` loads a Doc from plain data (a child names its component with
  `"type"`; a `Raw` field takes a string; pydantic's default coercion), `to_dict(node)` writes it back, `json_schema(cls)` exports
  the schema with the docstrings as descriptions. Every error comes at once as an `ExceptionGroup` of `ValidationError`
  (`TM-C020`) with the path `validate()` would give it. `pydantic` is a dependency.
- `texmodel.types.Choice` (T1): a closed set as a field type. A member's value is the TeX it stands for, a `Raw` (passes
  through) or a `str` (escaped); data names a member by its name and `to_dict` writes it back; the schema lists the names.
  A mixed or aliased set is refused at declaration (`TM-M024`); `validate()` names the choices (`TM-C003`).
- `texmodel check` also compares committed documents with what the model renders now (`[tool.texmodel.documents]`, committed
  file to pointer). A pointer may return a `Plan`: a changed, removed or added line is reported with the path of the component
  that writes it. `texmodel render` accepts a `Plan` too. There is no baseline file: the model is the reference.
- `Value[Text]` (M1a): a text setting. A generated package defines `\newcommand{\prefixName}{default}` (escaped); a document's
  `settings=[Name("R&D")]` writes `\renewcommand{\prefixName}{R\&D}` after `\usepackage`, before the preamble slot; other
  settings stay in the body. An adopted package may declare a `Value[Text]` (with no default): `check_interface` expects an
  argument-less definition. Other adopted values are refused (`TM-P005`).
- Typed references in bodies (§21a 17): `Fact.call(Hole("text"))` for a command (required arguments positional, the optional one by
  keyword), `Box.open(title=...)` / `Box.close()` for an environment. An argument is a `Hole` (`#name`), a `Raw`, a `str` (escaped)
  or a `Choice`; arity and types are checked when the piece is built (`TM-M026`). The target must be registered first
  (`TM-M019`). A target of another package, adopted or not, becomes a `\RequirePackage` (sorted, once; `Package.depends_on`,
  `required_packages`); packages that require each other are refused when rendered (`TM-P007`). `Ref.with_whitespace` sets a
  piece's policy. Example: `tests/examples/composed/`.
- Body pieces (M8, new module `texmodel.body`): a body, `begin` or `end` may be a string, a `TemplateRef`, a `TexRaw` or a
  sequence, iterator or generator of those. `TexRaw(body, whitespace=)` is dedented; `Whitespace.TRIM` adds `%` to each line end
  (not to lines that end with one, comments or blank lines) so line ends make no space; `KEEP` writes lines as given.
  `Package(whitespace=)` is the default for pieces that name none (`KEEP`). `TemplateRef` moves to `texmodel.body`.
  `\verb` in a `TRIM` piece is refused (`TM-M025`).
- `Package.plan(...)` (B2, D2): the document as `Plan`, lines with the path of what wrote them. `Plan.edits(text)` finds changed,
  removed and added lines by path, `path_of(n)` maps an output line (a log's `input line`) to its path, and `to_json` /
  `from_json` store it as a baseline beside the committed file. New module `texmodel.plan`.
- `tests/consumers/card_deck/`: a synthetic consumer (a hand-written package, the template generator it replaces, made-up
  cards), its model and converter, and Gate B tests that compare printed output, find hand edits by path, and compile the
  defect classes (interface drift, escaping, over-set).
- `tests/examples/`: complete example packages with committed output, compared by the test suite and compiled by the
  `tex` suite.
- `texmodel-build`: a second package in this repo (`harness/`) holding the compile and verify side; `texmodel` itself never
  spawns a process. Its configuration is `[tool.texmodel-build]`.
- `texmodel_build.Compiler`: a thin `latexmk` driver (host, or `docker run` over an image) returning a typed
  `CompileResult` with parsed diagnostics (`TM-X0xx`), page and pass counts, probes and tool versions; ordered asset
  roots, font directories, `--epoch`, convergence diagnostics, `clean`. `texmodel-build` has `compile`, `build` (targets
  from `[tool.texmodel-build.targets]`), `clean`, `verify` and `doctor`.
- Verifier plugins (`texmodel_build.verifiers` entry points) with the rule that anything unconfirmable fails; an optional
  adapter over proof-pdf (`texmodel-build[proof-pdf]`).
- `texmodel.drift` and `texmodel.bundle`: byte-for-byte drift detection (stale, missing, orphaned) and a manifest copy that
  refuses if any source is missing.
