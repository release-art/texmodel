# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.1] - 2026-10-26

### Fixed

- The README had unresolved merge conflict markers and a second copy of the guide; it is the short front page again.
- The guide called `validate()`, which is `violations()`.

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

Generated output changes only for a value written from a float (a long tail of digits becomes five decimals).

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

[Unreleased]: https://github.com/release-art/texmodel/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/release-art/texmodel/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/release-art/texmodel/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/release-art/texmodel/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/release-art/texmodel/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/release-art/texmodel/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/release-art/texmodel/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/release-art/texmodel/releases/tag/v0.2.0
