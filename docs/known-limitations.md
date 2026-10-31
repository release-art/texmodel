# Known limitations

What texmodel does not do or does not check today. Planned work is ordered in the roadmap (`docs/briefs/roadmap.md`) and specified in [the plan](texmodel-plan.md) (§19, §21a).

## Scope

- No TeX parser (plan N1). Interfaces are declared, never read back from TeX texmodel did not write. The adoption scanner
  (`check_interface`) reads `\newcommand`, `\providecommand`, `\DeclareRobustCommand`, `\newenvironment`, the xparse `\NewDocumentCommand` family,
  `\newlength`, `\newsavebox`, `\newfontfamily`, `\newtoggle`, `\newif`, `\definecolor`/`\colorlet` and `\newcounter`; a name
  defined another way counts as missing, and a library written in expl3 is not read, and an xparse type it does not model (`v`, `u`, `g`, `e`) is reported as
  `?` and matches nothing.
- Python 3.15 and LuaLaTeX only. Compiling needs the reference image (or a local TeX Live with `latexmk`).
- Not built here: releases and migrations, which are texpkg's (§13); trust levels and the injection corpus, the
  sandbox verification, `texmodel-print`, a rules layer, `List[T]` settings (`Value[...]` takes `Length`, `Colour`, `bool`,
  `Text`, `Raw`, and a package's own kinds such as etoolbox's `Toggle`).
- No check of what TeX would do with a value: a `Length` key is checked to be a length, not to be sensible for the package.
  Layout is not checked at all; `Overset` types a package's own "does not fit" warning.

## Packages on a base

- `base=` does not check that a package's own value replacing a base value of the same name has a compatible type, and the
  comment classes of `Package(comments=)` are not inherited from the base.

## Print output

- `PrintPage`'s trim, bleed and margin are declared once: a document chooses among the sheets the package's options
  give (full or trim, portrait or landscape), not other sizes. A landscape sheet needs symmetric sides (`TM-M074`).
  Boxes are the same on every page (no recto and verso with different inner margins), and the engine must be LuaTeX.
- A spot colour is declared once: a document cannot set it, and two values with the same plate name are a compile error
  (`Duplicated spot name`), not a declaration error. Plate names are checked only for what breaks the PDF name or TeX.
- `OutputIntent` knows PDF/X-4 and PDF/A-2b. It checks an ICC header, not that the profile is the one named by its
  condition, and whether a file is where the compile will look is the compiler's roots.

## Colours for print and screen

- A package option is a flag, a length or a choice; a text, a colour or a key list is a setting after `\usepackage`. A
  class option that names a package's key is not checked. A `Dual` colour is not a spot (no screen build) and not checked for agreement between
  its two builds: that is the consumer's colour conversion.

## Plates

- A colour is process (a subset of C, M, Y, K) or one spot: xcolor cannot mix a separation with CMYK, so `plates` sets that
  mix a spot with process plates describe a job, not a colour, and are not accepted on a value. A colour a library defines
  counts as a process colour in a mix, and the names of `dvipsnames` and the like are not known. `black` and the grays are the
  K plate in the `cmyk` model only.

## Recorded values

- `Recorded` takes a length or an integer and the folds `MAX`, `MIN` and `SUM`; no flag, list or text. A value that depends on
  its own measurement never settles: the run warns, and the author fixes it by measuring at a fixed size. Nothing stops a
  document setting the recorded value as it would any `Value`; it is measured, not set, by convention.

## Fitted text

- `Fit` shrinks to the floor and stops: a title wider than the measure there overflows, and the log names it. There is no
  wrapping. `reduced_sizes` is 0, 1 or 2 (a general N is a different algorithm). A size needs a scalable font (OpenType
  under LuaTeX, or `anyfontsize`).

## Arguments and key lists

- A definition needs LaTeX 2020-10 or later when its signature is not `\newcommand`-shaped (xparse is in the kernel from
  then). Hole numbers are `#1`...`#9`; a signature with more slots is not refused by texmodel, TeX refuses it.
- A `Hole` stands for a whole argument. It cannot sit inside a `KeyVals` or a tuple; build the list in the body with
  `Raw` pieces instead.
- Verbatim and delimited-by-token arguments are not modelled. Neither is an optional braced group (xparse `g`).
- A colour model (`CMYK`, `RGB`, `Gray`) writes its components, `0,0,0,1`, which suits `\definecolor` and
  `\color[cmyk]{...}`; a macro that wants a name takes `ColourName`, which the package checks (`TM-C022`).
- A `KeyVals` that fails its own checks (`exclusive`, `requires`, a wrong type) raises pydantic's `ValidationError` when it
  is built, not a `Violation` from `violations()`.
- Key libraries differ in ways the presets only partly capture. `KeyRules` was measured against pgfkeys, xkeyval, keyval
  and l3keys with a corpus of awkward values (`tests/test_texmodel/test_interface_tex.py`); `KVOPTIONS` was not. A space at
  the end of a value is kept by `{{ a }}` in three of the four and trimmed by `l3keys`; a library that treats braces
  differently from these needs its own `KeyRules`.
- A `Raw` value or `Item[Raw]` is written as given: texmodel checks only that its braces balance.
- The names `content` (an environment's children) and `type` (the component in data) are not usable as field names, nor
  any attribute every component has (`copy`, `json`, `render`, a `model_` name: `TM-M045`).
- pyright checks a command's and a `Passthrough`'s arguments, not an environment's keywords: `dataclass_transform` cannot
  describe positional children.

## Building

- `texmodel.run.fonts` reads the font listing LuaTeX ends its log with; a compile that stopped early has none, and a font
  inside an included PDF is never listed.
- `texmodel.run` is async only. Synchronous code calls it through `asyncio.run(...)`, which cannot run inside an event
  loop that is already running.
- A copy of texmodel embedded where its installed metadata cannot be read must set `texmodel.package.GENERATOR_VERSION`,
  or the stamp of generated files is the version of whichever texmodel is installed (or `0.0.0`).

## Hand edits

- `Edit.fields` is empty when a change is over a delimiter, the command name or several arguments, and for a call over
  several lines. A baseline saved before `Line.spans` gives node-level edits only.
- `read_edits` reads what TeX runs through stubs, so it does not see: an extra argument (`\x{a}{b}`: the group is typeset),
  an unstubbed line, a body error a value causes (the stubs never run bodies, so a compile that passes is not the document
  compiling), or a stubbed macro the text redefines (its calls vanish). A missing argument swallows the next call, so one
  edit reads as two. Those lines come back as `UNREAD` or `ADDED`/`REMOVED` from the line diff, never as clean.
- An omitted optional argument and an empty one (`[]`) are the same call. Spaces in text read back as one. Equal neighbouring
  calls have no identity: a deleted one is named by position. A move across environments reads as the close moved.
- A key list, a PDF string, a `Raw` subclass and a colour in a `Value` are not read (no value, no violation); a record
  reads as a plain tuple; a length written `3 cm` is read, and `3mm` against `0.3 cm` are two values.
- `restore` does not restore an added line, a setting, the preamble or a comment: they come back unapplied with their
  `Reason`. A call over several lines and a change over a delimiter or the command name are `NOT_IN_ARGUMENT`. A field
  these readers do not read (above) is `UNREADABLE`; a colour reads as its parts, not its model, so it is too.
- A comment-out is only `%`, spaces and the line unchanged; a line commented and edited, or `%%`, is a `PARTIAL_REMOVAL`.
- An optional argument restored to its default is stored as set (`"label": null` in `to_dict`), not left out.

## The standard headers

- `texmodel.std` covers the commands a deck uses, not each package. `adjustbox`, `graphicx`, `geometry`, `tcolorbox` and `tikz`
  type their common keys and take the rest as `Item[Raw]`; the other headers still take `Raw` for options and lengths.
- `calc`: a parenthesised integer expression after `*` or `/` (`2cm*(1+2)`) works in TeX Live 2025's `calc` but is not in its
  documented grammar, which allows only a number, `\real`, `\ratio`, `\maxof` or `\minof` there. The header allows it.
  `\relax` scan stops are not modelled. A `DimenExpr` fits the commands that read lengths through `\setlength` (checked for
  `\makebox`, `\raisebox`, `\parbox`, `\hspace`, `\vspace`, `\rule`, `minipage`, `p{}`); `\fontsize` and `\hskip` take
  primitives and refuse it, and nothing stops you passing one to a `Length` field of such a command.
- `tabularray`: `colspec` and `rowspec` are `Raw` (their language is not modelled), the experimental interfaces (child ids and
  classes, hooks, public variables) and the `functional` library's functions are not typed, and the `amsmath` library's
  `+matrix`, `+array` and `+cases` environments are not declared: an environment name has letters only (`TM-M027`).
- `ext.table`: a `collect`ed `TableEnvironment` allocates one box register per use (never freed) and cannot hold a `long` table; a `TableEnvironment` holds rows that are nodes only, with no header, groups, totals or spans (a plain `Table` sets those, and writes its layout into the document); `Widest` sets its column to nothing on the first run (rerun until settled), measures the cell text and not its group or footnote marks, and a cell that does not typeset the same on every pass never settles; a row command that calls another row command is listed in `expand` by hand, reordering or adding a row line is not restorable (`TM-R006`, `TM-R005`), a `TableRow` has no optional argument or `\multicolumn` (use `\SetCell`), `read_edits` does not stub the `booktabs` library's tables; no footnote marks in cells, no `rowspan`, no `\verb` or `\footnote` in a cell, `blocks=True` and `Image` do not load `varwidth` or `graphicx` (the document's package does), no header cells that merge vertically over a column without a group, and
  no number alignment by decimal point at mixed precision. A `Table` is a builder, not a component, so it is not in a document's data or schema.
- `ext.graphics`: a figure holds one picture, with no sub-figures, side-by-side pictures or maximum size (that is `adjustbox`);
  `alt` and `artifact` are LaTeX 2024-11 keys, an older kernel refuses them.
- `tests/test_std` proves a call is accepted by TeX, not that it does what the name suggests. A library the reference image
  lacks makes its test skip (a failure under `TEXMODEL_REQUIRE_TEX=1`).
- TikZ paths (`\draw`, `\node`) are written as `Passthrough` or `Raw`.
