# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.11.0] - 2026-10-30

Output change: a package with a `ColourSpace` declares `cmyk` and `rgb` as l3keys options in an options section.

### Added

- `texmodel check` says what an upgrade explains of a stale generated file written by another version: only its version
  line, the releases in between that changed generated output and how, or none, so the rest is a hand edit or a change to
  the declarations. `texmodel.drift.OUTPUT_CHANGES` lists those releases (0.3.0, 0.3.2, 0.8.0, 0.10.0 and 0.11.0); each changelog
  section that changes output starts with an `Output change:` line.
- `texmodel.history`, one model's history (plan §13), moved from texpkg: `problems(model, data, schema)` (what stops stored
  data from being a valid tree: pydantic's errors with the field's schema, then the grammar's violations) and
  `unplaced(data, schema)` (stored fields the model no longer has), each a `Problem(path, reason, value, schema)` with a
  data path; `schema_changes(old, new)`, two JSON Schemas of one model as `Change`s with a `Level` (`NONE`, `REVISION`,
  `COMPATIBLE`, `BREAKING`, by Avro-style rules), and `worst`. Releases and migrations stay in texpkg, which imports these.
- Package options: `Package.option(name, flag= | length= | choice=, inverse=, doc=, cs=)` declares one and returns the
  value it sets; `Package.options` lists them. Every option is a key of the l3keys family named after the package, set
  only while it loads and processed once by `\ProcessKeyOptions`, in an options section right after the `\RequirePackage`
  lines; the register it sets is LaTeX2e's (`\newif`, `\newlength`, `\newcommand`). The same declaration again is the
  same option, so modules share one; another is `TM-M073`; a name or a kind that cannot work is `TM-M072`. A document
  sets an option as any value, and it is written in `\usepackage[crop=false,bleed=2mm]{...}` (a base's option is passed
  to the base first).
- `PrintPage.declare(pkg, full=, landscape=)`: flag options choose the full sheet or the trim alone, and a landscape sheet
  (the trim and its sides turned 90°, `TM-M074` unless they are symmetric), when the package loads; every sheet is written
  as numbers in `\if` branches (`TM-M075` for a switch that is not a flag option). `PrintPage(marks=True)` draws crop
  marks on the full sheet (`showcrop`).
- `texmodel.restore.restore(pkg, document, edits)`: the document that writes a hand-edited file, from the document
  texmodel last wrote and its plan's edits (or `read_edits`'). A changed argument restores as its field's new value; a
  node deleted, or commented out as itself, is removed when its parent's grammar allows. Each edit is applied only when
  the document with it writes the edited line exactly; every other comes back in `unapplied` with a `Reason`, one
  registry of stable `TM-R001`-`TM-R011` codes. Edits of another document are refused (`TM-X034`).
- `Edit.line` (1-based, in the edited file; `None` for a removed line or an edit only TeX saw) and `Edit.file`, given as
  `Plan.edits(text, file=path)` or `read_edits(..., file=path)`; `Edit.plan_line`, the plan line an edit is about (for
  an added line, the one it follows), which `restore` reads instead of matching text.
- An added line's `Unapplied` names the node it stands in (`parent`) and the child it follows (`after`).
- `plan.BEGIN_DOCUMENT`, the plan's `\begin{document}` line.
- `plan.data_path(path)` and `Edit.data_path`: where a plan line's writer is in the document's `to_dict` data, a
  `PurePosixPath` (`/content/1/content/0`, `/settings/2`, `/preamble/after_package/0`).

### Changed

- `ColourSpace` declares the package option `cmyk`, with its inverse `rgb`, through `Package.option`: it may be declared
  anywhere in the package, twice the same way is one option, and a document may set its flag (`\usepackage[cmyk=false]`)
  as well as pass the class option `rgb`.
- `texmodel_build` is `texmodel.run`, a subpackage of `texmodel` (`from texmodel.run.compiler import Compiler`). The
  core never imports it: an exhaustive import-linter layers contract (`cli` above `run` above every core module).
- One command: `texmodel-build <command>` is `texmodel run <command>` (`compile`, `build`, `clean`, `verify`,
  `doctor`); `texmodel -v` sets the logging for both.
- The configuration table `[tool.texmodel-build]` is `[tool.texmodel.run]` (`.targets`, `.profiles`, `.measures`,
  `.exempt` under it); the verifier entry-point group `texmodel_build.verifiers` is `texmodel.run.verifiers`.
- Async: `Compiler.compile`, `clean`, `check_ready`, `missing_files`, `versions()` and `image_info()` (methods, no
  longer properties), `build_targets`, `run_probes`, `check_library`, `check_verifier_contract`, `read_edits`,
  `verify_file`, `verify_files` and `Verifier.verify` are coroutines. A compile that times out or is cancelled kills
  its process group (`latexmk` and the engine it started) and, in the image, its container.
  `build_targets` and `verify_files` run `jobs` in a `TaskGroup`.

### Removed

- `texmodel.ext.colourspace.LIBRARY`, and the rule that `ColourSpace` comes before the colours (`TM-M065` now means only a
  package without a prefix): its option is in the options section, before every colour.

### Fixed

- `Plan.edits` pairs a line with itself commented out or re-spaced inside a replaced block, so deleting one line and
  commenting out the next names each by its own path; a line the same on both sides of a block (difflib's autojunk on a
  long file) is no longer an edit.
- `read_edits` reports a call commented out on its line as one `REMOVED` edit, not `UNREAD` and `REMOVED`.

## [0.10.0] - 2026-10-29

Output change: `ext.fit` declares its two public lengths with `\newlength`.

### Added

- `Package.make_command` and `make_value` take `defined_by=`, a library block that defines the command or value; a command
  made so has no `body`.

### Changed

- `texmodel.ext.fit` declares its two public lengths, `\<prefix><Name>Size` and `\<prefix><Name>LineSize`, with
  `\newlength` (was `\dim_new:N`), so `declared()` and the adoption scanner read them. A package that declares a `Fit`
  renders a different `.sty`.
- `ColourName` checks its whole grammar (`name!50!name`, numbers up to 100) when it is built (`TM-M067`), not when
  `names` is read.
- `texmodel check` on an adopted package reports a public `<prefix>Name` the hand-written sources define that nothing
  declares (`TM-C025`), as it reports a library's (`TM-C012`): a check that passed may now fail until the name is declared
  or renamed with an `@`.
- A compile places a line that names no file of its own (a package warning's `on input line N`, a box, a `! message`) in
  the file open at that point: LuaLaTeX runs a `start_file`/`stop_file` callback before the document (latexmk's
  `-pretex`, the engine's command is `%O %P`) that marks each TeX file in the log. A warning raised in an `\input` part or
  in a package while it loads names that file, and is no longer mapped to a line of the main document; a line in no file
  is not mapped. The PDF is unchanged; the log gains `texmodel:open:<name>` and `texmodel:close` lines.
- `TM-T004` says "docker could not start the container" when `docker run` itself fails (exit 125), and "could not run
  latexmk" only when latexmk is missing.

### Removed

- `texmodel.ext.plates.is_single_plate`: `len(plates_of(colour)) <= 1`.
- `texmodel.ext.recorded.reduce` and `Fold.kinds`: `fold.reduce(values)` and `fold.update`.
- Plumbing that was public by name only moves to `texmodel._internal`: `spec_of`, `env_spec_of`, `value_spec_of`,
  `call_line`, `emit` and `INDENT` (`texmodel.components`), `body_of`, `record_fields`, `field_info` and `FieldNotes`
  (`texmodel.interface`), and `inline_text` and `text_of` (`texmodel.body`).
- `texmodel.body.join`, which writes a body's pieces as TeX, moves to `texmodel._internal` with them.

## [0.9.0] - 2026-10-29

### Changed

- `ColourName` is a `str` subclass you can build: `ColourName(Ink, tint=0.7)` is `ab-ink!70`, `mix=` gives `a!70!b`, and
  `tint` is a fraction. Both ends of a mix may ink the same plates and no others (`TM-M068` when built from values,
  `TM-C024` for any expression a node checks). A field typed `ColourName` is checked against its package: a colour value of the package or its base,
  a colour one of its LaTeX libraries defines, or an xcolor base name; anything else is `TM-C022`, and an expression that is
  not `name!50!name` is `TM-C023`. A plain string still loads and renders, but a type checker now asks for `ColourName(...)`.
  `COLOUR_NAME` is gone from `texmodel.interface`.
- `colour_of(Value)`, the xcolor name of a colour value, moves to `texmodel.interface` (`texmodel.ext.colourspace` still
  exports it).

### Added

- `texmodel.ext`, next to `std`, for opinionated helpers; its first module is `texmodel.ext.plates`: `K(fraction)`, a colour
  on the black plate only (`K.nearest` rounds to a step), and `is_single_plate`. `Value.plates` is the set of plates a
  colour value may ink (`{Plate.K}`: K only, `{Plate.C, Plate.M}`: a duotone); a default, a setting or data outside it is
  refused (`TM-M070`). `plates_of(colour)` names the plates any colour inks, and `Plate` the process ones; a spot is its own
  plate.
- `texmodel.ext.printpage`: `PrintPage(width=, height=, bleed=, overflow=, margin=)` writes the `\geometry` call and the PDF
  page boxes (`/TrimBox`, `/BleedBox`, `/CropBox`) from the trim, edge by edge (`Sides`: `all=`, `horizontal=`/`vertical=`
  or the four edges). `Sheet.TRIM` is a review copy with the same type area.
- `texmodel.ext.colourspace`: `ColourPair(cmyk=, rgb=)` and `Value[Dual]`, a colour with a print build and a screen build under
  one xcolor name, chosen by the package options `cmyk` and `rgb` that `ColourSpace` declares (a document passes one with
  `Document(options=["rgb"])`); `colour_of(Value)`, the xcolor name of any colour value.
- `texmodel.ext.fit`: `Fit(name, target=, floor=, room=, treatment=, reduced_sizes=)` sets a short line to fit a band at one
  main size for the whole document, a few shared smaller sizes (0, 1 or 2) for the lines that cannot reach it, never below
  the floor, on one baseline; the widths are recorded in one run and used in the next. `choose_sizes` is the rule in Python.
  `texmodel.ext.recorded` gains `LENGTHS` (a list of lengths) and the `APPEND` fold for it.
- `texmodel.ext.recorded`: `Recorded(name, kind=, fold=)`, a value only the whole document knows (the widest label, the
  number of cards), carried between runs through the `.aux` with the `\global`, the guarded read and the "not settled" warning
  done once. `Fold` is data: `MAX`, `MIN`, `SUM` over a length or an integer, each with its Python `reduce`.
- `texmodel.ext.spot`: `Spot(plate, proxy=)` and `Value[SpotColour]`, a named plate on the press (`\definespotcolor`, from
  `colorspace`) with a CMYK proxy, and `ColourName(Varnish, tint=0.6)`, xcolor's `ap-varnish!60`. A plate name with a PDF delimiter is
  refused (`TM-M053`); a spot is declared once, not set by a document (`TM-M055`). The test image gains `colorspace`.
- `texmodel.ext.intent`: `OutputIntent` writes the `\DocumentMetadata` keys of PDF/X and PDF/A with an intent of the same
  condition each, and registers the ICC profile's output condition, without which l3pdfmeta writes no intent;
  `OutputCondition.check_profile` reads an ICC header.

## [0.8.0] - 2026-10-28

Output change: a document's body is indented two spaces per level of environment.

### Changed

- A document's body is indented two spaces per level of environment: an environment's `\begin` and `\end` take its depth,
  its children one level more, and `Environment.render()` writes the same text as the plan. Only the lines texmodel writes
  are indented (the first line of a call, `\begin`, `\end`, comments): a `Passthrough` and the later lines of a call are
  verbatim. The spans of a line move with the indent. Every generated document changes, so `texmodel check` reports a
  committed one stale until it is rendered again, and a plan saved before reads every indented line as an edit.

## [0.7.0] - 2026-10-27

### Added

- `Package(..., base=other)`: a package that specializes another. `.base` is the link; the `.sty` starts with
  `\RequirePackage{other}`; `visible` and `value_named(name)` look through the base chain, and a name the package declares
  itself replaces the base's. `from_dict(package, ...)`, `json_schema(package)` and a document's slots use `visible` and
  the base's control sequences, so a document of the derived package holds the base's nodes and settings.

## [0.6.0] - 2026-10-26

### Changed

- A command's fields are keyword-only: `Fact(text="a")`, not `Fact("a")` (`TypeError` otherwise, and a type checker flags
  it). A class opts out with `class X(Command, kw_only=False)`, which a subclass inherits. An environment's positional
  arguments are still its children; `Passthrough(Raw(...))` stays positional. `repr(node)` writes the keywords.

## [0.5.1] - 2026-10-26

### Added

- `texmodel.document.Document(*content, options=, settings=, preamble=)`: a document as one value. Its settings, class
  options and preamble entries are in the tree, so they round-trip through `to_dict` and `from_dict(package, data)`, are in
  `json_schema(package)` (its root) and have paths in the plan (`settings[0]`, `preamble.after_package[1]`), where a hand
  edit to them is found. An entry in the wrong slot is still `TM-C008`.
- `from_dict(package, data)` returns the `Document` of a package; `to_dict` takes one.

### Changed

- `Package.plan`, `document` and `test_document` take one `Document`, or bare nodes. `PreambleSlots` is in
  `texmodel.preamble`.
- `json_schema(package)` has a root (`$ref` to its `Document`) and `$defs` entries for it, the preamble entries and
  `<Name>Setting` per value.

### Removed

- The `settings=`, `options=` and `preamble=` keywords of `Package.plan`, `document` and `test_document`: put them in a
  `Document`. `texmodel.package.PreambleSlots` (now `texmodel.preamble.PreambleSlots`).

## [0.4.1] - 2026-10-26

### Added

- `Description.body` and `Description.end`: the declared TeX of a command or environment, with `#name` holes, so a package's tests can assert a body without reading `__tm_tex__`.

### Fixed

- The README had unresolved merge conflict markers and a second copy of the guide; it is the short front page again.
- The guide called `validate()`, which is `violations()`.
- The guide describes what a node is (`model_fields_set`, frozen) and `GENERATOR_VERSION`; the pull request template asks for
  a changelog line, not a fragment.

## [0.4.0] - 2026-10-26

Components are frozen pydantic models. A hand edit is named by argument and read by TeX.

### Added

- `Plan.edits` names the argument a hand edit changed: `Line.spans`, `Edit.fields` and `FieldEdit(arg, found, value,
  violation)`; empty unless the change is inside one argument. `EditKind.UNREAD` is a line that differs while TeX reads
  the same calls.
- `texmodel_build.hand_edits.read_edits(compiler, plan, text, *packages)`: the edits read by TeX through stubs, each
  changed argument with its typed value or the `Violation` (`TM-C021`) saying it holds none. `TM-X032` (the plan's calls
  and lines disagree), `TM-X033` (no component to stub).
- `texmodel.testing.read_call(cls, call)`: a stub's call as typed `FieldEdit`s. `components.call_line(node)`.
- `texmodel_build.fonts` (`embedded`, `outside`): the font files a compile embedded, from its LuaTeX log, and those
  outside the allowed directories.
- `texmodel.package.GENERATOR_VERSION`: when set, `generator_version()` uses it instead of the installed metadata, for a
  copy of texmodel embedded in a wheel.
- `node.model_fields_set`: the fields the caller passed, positionally or by keyword, or the keys the data gave to
  `from_dict`.
- `Package(comments=[...])`: the `Comment` subclasses data may hold in the package's environments.
- `TM-M045`: a field named like an attribute every component has (`copy`, `json`, `render`, a `model_` name).
- The guide under `docs/` (built with MkDocs Material: `pdm install -G docs`, `pdm run mkdocs serve`); every `python`
  block in the README and the docs is run by `tests/test_docs.py`.

### Changed

- `Command`, `Environment` and `Passthrough` are frozen pydantic models. Building one validates nothing; assigning to a
  field raises `pydantic.ValidationError`; `str(node)` is `repr(node)`.
- `validate()` is renamed `violations()`, on components and `Comment`.
- `to_dict` writes the fields a node was given (`model_fields_set`), `None` and `False` included when given, and leaves out
  a default that was not.
- `field()` and `arg()` return a pydantic `FieldInfo`; a field's doc, old name and `x-` keys are in its schema from it.
- An environment's JSON Schema has its docstring as `description`, as a command's has.
- `Plan.to_json` writes a line's spans as a third element when it has any; a baseline without them loads.
- A `TemplateRef` is read through `importlib.resources`, so a declaration imported from a zip finds its templates.
- Every public module has an `__all__` naming its API.

### Removed

- The `comments=` argument of `from_dict` and `json_schema`: list the classes on the package.
- `pointer.load_package`: `load_packages` takes one pointer.
- `texmodel.spec.ValidationError`: import it from `texmodel.errors`.
- `body.refs_in`, `syntaxes_in`, `pieces_of`, `template_text`, `plan.node_lines`, `preamble.tex_of` (internal now).
- `texmodel_build.roots` (`resolve`, `shadowing`, `Resolution`, `TM-C100`).

## [0.3.3] - 2026-10-23

### Added

- `InputIfExists(name)`: a typed preamble entry, `\InputIfFileExists{name}{}{}`, for `before_package` or `after_package`
  (`TM-M044` for a name that is not a file name).
- `Package.make_command` and `Package.make_value`: declare and register a command or value from data. The same data under
  one name returns the class made first; other data is `TM-M007`.
- `describe(cls)`, `Description` and `ArgumentInfo` (`texmodel.components`): a registered command, environment or value as
  frozen data, so a program need not read the `__tm_*` attributes.
- `texmodel.package.declared(text)`: the control sequences the adoption scanner reads in a text, as a `frozenset`.
- `texmodel.package.setting_line(value)`: the line a document writes for one setting; `Package.plan` uses it.

## [0.3.2] - 2026-10-23

Output change: a value written from a float has five decimals.

### Changed

- Floats are rounded to five decimals where they are written: a `Length` made from a float (`Length(0.1 + 0.2, "mm")` is
  `0.3mm`), float fields and `calc` numbers, as colour components already were. A string keeps every digit.

## [0.3.1] - 2026-10-22

### Added

- `abstract=True` on a `Command` or `Environment`: a shared base that carries fields, `body` (or `begin` and `end`) and
  `children` for its subclasses, needs no docstring or control-word name, and is never registered (`TM-M043`).
- `Value.declared_default()`, and `control_name(value)`: a value's control sequence (`__tm_cs__`); a colour has none
  (`TM-M042`).

## [0.3.0] - 2026-10-22

Output change: defaults in definitions, dateless `\ProvidesPackage`, settings after `\usepackage`, 5-decimal colours.

Parts and models: a package can be a list of TeX parts filled from typed models, checked against the components that call
them. Value kinds are data, so a package adds its own.

### Added

- `Package.library(..., fill=model)`: `<<name>>` holes (`<<a.b>>` into a nested model) filled by type from a mapping,
  dataclass or pydantic model; `str` is escaped, `Raw` passes through, lengths, colours, numbers and flags are written as
  they are. `TM-M040`, `TM-M041`.
- `texmodel check` reads every library (`Package.check_parts()`): a component or value that names it with `defined_by` must
  be defined with its signature (`TM-C010`, `TM-C011`), a public `<prefix>Name` it defines must be declared (`TM-C012`),
  and a name defined twice is reported (`TM-C013`) and refuses generation (`TM-P012`). The scan also reads
  `\DeclareRobustCommand`, `\newlength`, `\newsavebox`, `\newfontfamily`, `\newtoggle`, `\newif` (with `\Xtrue` and
  `\Xfalse`), `\definecolor`, `\colorlet` and `\newcounter`.
- A `Value` can be defined by a library (`defined_by`): a flag, toggle, length, colour or text setting the part declares
  renders nothing and has no default. `cs` names a value's whole control sequence; `colour_name` a colour's name; a
  `Value[Length]` may have no default (a bare `\newlength`).
- `ValueKind` (`texmodel.types`): what a `Value[T]` is, as data. `texmodel.std.etoolbox.Toggle` is the first kind a package
  adds (`\newtoggle`, `\toggletrue`); a kind's `needs` may name a `Package`.
- `[tool.texmodel] package` may be a list of pointers, or a pointer to an iterable of packages; `build` and `check` cover
  the family together (`TM-D026`).
- `Package(date=None, header="...")`: a package with no date has no `\ProvidesPackage` bracket, and `header` adds comment
  lines under the generator's line.
- `field(doc=, meta=)`, `arg(doc=, meta=)` and a class-level `meta`: carried into the JSON Schema as `description` and
  `x-` keys.
- An optional argument's `Text`, `Raw`, number, flag or `Choice` default is written in the definition
  (`\newcommand{\acRating}[2][\acMark]{...}`).
- A `Raw` argument may hold calls (a `Ref`, or a `Seq` of pieces), so a conditional's branch can call a declared component.
- `texmodel.std.etoolbox`: `ifnumgreater`, `ifnumless`, `ifnumequal`.
- `docs/cookbook.md`: worked examples (settings, defaults, counting rules in TeX, schema metadata, parts filled from a
  model, a family of packages), run by the test suite.
- Macro interfaces (`texmodel.interface`): `arg()` states how a field is written (delimiters
  `{}` `[]` `()` `<>`, several optional arguments with `fill=`, `Star` and other tokens, `SlotGroup`), and fields may be
  `Length` (`Length.expr` for a TeX expression), `Colour`, `ColourName`, `int`, `float`, `bool`, tuples and records, lists and
  key lists. A signature `\newcommand` cannot define is defined with `\NewDocumentCommand`; stubs and the interface check
  read it.
- `texmodel.std.calc`: the whole `calc` package as a typed expression language. `IntExpr`, `DimenExpr` and `GlueExpr` with
  `+ - * /`, `real`, `ratio`, `widthof` and the other text sizes, `maxof`, `minof`, and the commands it extends or adds.
  Mistakes TeX would refuse (`2cm+4`) are a `TypeError`; the values are checked by compiling.
- Key lists: `KeyVals` (`texmodel.keyvals`) with `Flag`, `Switch`, `Item`, `OptionalValue`, nested and repeated keys, and
  `KeyRules` presets for pgfkeys, xkeyval, keyval, kvoptions and l3keys (`texmodel.keys`).

### Changed

- `texmodel.std`: `adjustbox`, `graphicx`, `geometry`, `tcolorbox` and `tikz` take typed key lists instead of `Raw`;
  `\vspace`, `\hspace`, `\setlength`, `\addtolength` and `minipage` take a `Length`; added `\makebox`, `\raisebox` and the
  sectioning commands.
- `TM-M003` (more than one optional argument) is removed; an optional argument followed by another that says nothing
  about being skipped is `TM-M037`.
- `document(settings=)` writes every setting right after `\usepackage`, in the order given, before the `after_package`
  slot.
- `\ProvidesPackage` has no date unless the package gives one; with none, its version and
  description are a comment line, because LaTeX reads the first word of the bracket as a date.
- An optional argument with a scalar default is defined with it: an optional `bool = False` is `[false]`, not `[]`.
  Regenerate committed `.sty` files.
- Colour components are written to five decimals (`0.788`, not `0.7879999999999999`).
- `texmodel schema` needs one package; `texmodel check` also checks every library of every package.
- A component with a body that another source defines (a library block, or an adopted package) is one refusal, `TM-M032`
  (`TM-M023` is removed). `field()` no longer requires `renamed_from`.

### Fixed

- The scanner no longer reads a definer written out with `\string` or `\noexpand` (`\string\providecommand\string\x`)
  as a definition, and a command definer needs a backslash name, an environment definer `{name}`.

## [0.2.0] - 2026-10-22

First release (0.1.0 was never published).

- `texmodel`: declare LaTeX components (`Command`, `Environment`, `Value[T]`) as typed Python classes and render a
  deterministic `.sty`, documents and a JSON schema; check committed output for drift; adopt hand-written TeX; a standard
  library of headers (`texmodel.std`).
- `texmodel_build` and the `texmodel-build` command: a `latexmk` driver with typed diagnostics, and verifier plugins
  (`texmodel[proof-pdf]`).

[Unreleased]: https://github.com/release-art/texmodel/compare/v0.11.0...HEAD
[0.11.0]: https://github.com/release-art/texmodel/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/release-art/texmodel/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/release-art/texmodel/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/release-art/texmodel/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/release-art/texmodel/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/release-art/texmodel/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/release-art/texmodel/compare/v0.4.1...v0.5.1
[0.4.1]: https://github.com/release-art/texmodel/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/release-art/texmodel/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/release-art/texmodel/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/release-art/texmodel/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/release-art/texmodel/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/release-art/texmodel/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/release-art/texmodel/releases/tag/v0.2.0
