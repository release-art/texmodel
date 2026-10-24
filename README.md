# texmodel

[![CI](https://github.com/release-art/texmodel/actions/workflows/ci.yml/badge.svg)](https://github.com/release-art/texmodel/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Declare a LaTeX document family once in Python types; get plain, readable, git-trackable `.sty` source out of it. The output
is ordinary TeX: commit it, diff it, compile it with whatever LaTeX setup you already have.

> **Status: alpha.** The public API may change before 1.0. Release migrations, `texmodel-print` and the trust
> and sandbox layers are planned, not built (see [the plan](docs/texmodel-plan.md)). What is missing today:
> [known limitations](docs/known-limitations.md).

```zsh
pip install texmodel                 # the library and the texmodel-build command
pip install 'texmodel[proof-pdf]'    # plus the proof-pdf verifier
```

One distribution, two packages:

| Package | What it is |
|---|---|
| **`texmodel`** (`src/`) | The library: declare components, render deterministic TeX, check that committed output is current. No TeX needed, no processes spawned. |
| **`texmodel_build`** (command `texmodel-build`) | Optional: a thin `latexmk` driver with typed log diagnostics, and verifier plugins for built PDFs. Use it if you want compile results as data; your own `latexmk` or image works just as well. |

## texmodel

Worked examples and practices: [the cookbook](docs/cookbook.md).

```python
# acme_cards/__init__.py
from texmodel.body import TemplateRef
from texmodel.components import Command, Environment, Value
from texmodel.package import Package
from texmodel.types import CMYK, Colour, Length, Text

pkg = Package("acme-cards", prefix="ac", version="1.4.0", date="2026/10/21")
# `date=None` leaves the date out of \ProvidesPackage; `header="..."` adds comment lines under the generator's line

@pkg.value
class FactGap(Value[Length]):
    """Space under each fact."""
    default = Length("2mm")

@pkg.value
class Ink(Value[Colour]):
    """The text colour."""
    default = CMYK(0, 0, 0, 0.95)

@pkg.value
class Compact(Value[bool]):
    """Tighten the layout."""
    default = False

@pkg.command
class Fact(Command):
    """One short sentence under the title."""
    text: Text
    body = TemplateRef("fact.tex")   # explicit: a file next to this module; nothing is found by name

@pkg.command
class Slot(Command):
    """A labelled paragraph; the label prints as its heading."""
    text: Text
    label: Text | None = None      # optional: keyword-only, TeX's one optional argument

@pkg.environment
class CardBack(Environment):
    """The back face of a card."""
    children = [Name, Fact.times(2, 3), Slot.times(3)]   # in order: Name once, Fact 2 to 3, Slot 0 to 3; also X.times.any(), X.times.at_least_one()
    begin = r"\begin{minipage}{\linewidth}"
    end = r"\end{minipage}"
```

A body is TeX you point at: a `TemplateRef("fact.tex")` (relative to the defining module), a string, or a `body`
method returning either (dedented, so a raw triple-quoted string reads as it renders). `#text` is the argument named `text`:

```latex
\par\noindent{\color{ac-ink}#text}\par\vspace{\acFactGap}
\ifacCompact\vspace{-\acFactGap}\fi
```

A `Value[T]` needs no body: its type decides the declaration (`Length` -> `\newlength` + `\setlength`, `Colour` ->
`\definecolor` named `ac-ink`, `Bool` -> `\newif`), and its `default` is an instance of `T`. Packages a value needs
(`xcolor` for colours) are `\RequirePackage`d once, sorted. A body that names an undeclared `\acThing` is refused when
`render()` / `texmodel check` runs (not at registration, since a body may name a component declared after it).

A body may also be a `TexRaw` or a sequence or generator of pieces (strings, `TemplateRef`s, `TexRaw`s), each with its own
`Whitespace` policy: `TRIM` writes the `%` at line ends for you, `KEEP` (the default, set per package with
`Package(whitespace=)`) writes lines as given.

```python
from texmodel.body import TexRaw, Whitespace

def body(self):
    yield TexRaw(r"""
        \par\noindent
        {\color{ac-ink}#text}
    """, whitespace=Whitespace.TRIM)       # \par\noindent%  {\color{ac-ink}#1}%
    yield r"\par"
```

A body can call another component by Python binding. The call is checked against the target's arguments, written with the
target's prefix, and a target in another package makes that package a `\RequirePackage` of the generated `.sty`:

```python
from texmodel.body import Hole

class Entry(Command):
    """A fact with a rule above it."""
    text: Text

    def body(self):
        yield r"\par\hrule"
        yield Fact.call(Hole("text"))            # \bkFact{#1}; Fact belongs to base-kit, so \RequirePackage{base-kit}

class Section(Environment):
    """A titled panel."""
    begin = Panel.open(title=Hole("title"))      # \begin{bkPanel}{#1}
    end = Panel.close()                          # \end{bkPanel}
    title: Text
```

`Fact.call(...)` takes the required arguments positionally and the optional one by keyword (`Slot.call(Hole("t"), label="x")`);
an environment's arguments are all keywords. A target must be registered before the body that calls it.

An environment has `begin` and `end` in the same way. A document is plain
Python; `Text` fields are escaped, a `Raw` field passes TeX through, and everything wrong is reported at once:

```python
tex = pkg.document(
    CardBack(Name("Rex"), Fact("Friendly & loyal."), Fact("50% of $5")),
    settings=[FactGap(Length("3mm"))],       # values for the whole document
    options=["a4paper"],
)
CardBack(Fact("x")).violations()   # [Violation(TM-C002 ...), Violation(TM-C001 path='CardBack/Fact[0]' ...)]
```

```toml
# pyproject.toml
[tool.texmodel]
package = "acme_cards:pkg"
output = "generated"
```

A pointer (`package =`, and the argument of `texmodel render`) is `dotted.module:object`, `dotted.module:namespace.object`
(attributes are followed) or `dotted.module:getter()` (called with no arguments; its result is used):

```toml
package = "acme_cards.decks:Decks.birds"      # or "acme_cards.decks:make_package()"
```

A family of packages (a core, its bases, one per series) is a list of pointers, or one pointer to an iterable of
`Package`s; `build` and `check` cover them all together (a package name must be unique, as it is a file):

```toml
package = ["acme_cards.core:pkg", "acme_cards.birds:pkg"]      # or "acme_cards.family:all_packages()"
```

`texmodel schema` describes one package's data, so it needs a single `package`.

```zsh
texmodel build     # writes generated/acme-cards.sty
texmodel render docs:card   # writes card.tex from `card = pkg.document(...)` (or a function returning one); -o to choose
texmodel check     # exit 1 if a committed generated file is stale, missing or orphaned; a stale line names its component
                   # (`changed generated/acme-cards.sty Fact: ...`)
```

```latex
% generated/acme-cards.sty (excerpt)
\RequirePackage{xcolor}

% Space under each fact.
% from acme_cards.FactGap (value: Length)
\newlength{\acFactGap}
\setlength{\acFactGap}{2mm}

% The text colour.
% from acme_cards.Ink (value: Colour)
\definecolor{ac-ink}{cmyk}{0,0,0,0.95}
```

- **Deterministic**: no timestamps or hashes; the header records the generator version (`generated with texmodel X.Y.Z`),
  so `check` can say "written by 0.1.0, current is 0.2.0".
- **Checked early**: a bad declaration is refused when the class is defined, with a stable code (`TM-M0xx`) and the class
  named: more than one optional argument, a name that is not a TeX control word, a missing or ambiguous body, a `#name` that
  is not a field, an argument the body never uses, unbalanced braces, a name collision.
- **Typed**: `Fact("A soft woof.")` type-checks; fields are `Text`, `Raw` or either `| None`; values are `Length`, `CMYK`/`RGB`/`Gray` (components in [0, 1], no conversion between models) or `bool`.

### Shared bases

Components that repeat a body or a grammar share a base declared `abstract=True`. It carries fields, `body` (or `begin` and
`end`) and `children`; it needs no docstring and may have any Python name (`_Image`); it is never registered
(`TM-M043`), and its subclasses inherit all of it:

```python
class _Image(Command, abstract=True):
    src: Text
    def body(self): return r"\includegraphics{#src}"

@pkg.command
class Photo(_Image):
    '''A photo.'''
```

### Generating a body

A body can also be built from pieces that are well-formed by construction, so a generator cannot write an unbalanced brace or
a bad control word. `Group(...)` is `{...}`, `Seq(...)` the same without braces, `Cs("par")` a control word (letters and `@`
only, else `TM-M027`; `_` and `:` too in `Syntax.EXPL3`), `Lit("50% & co")` text escaped as a `Text` field is, and `Hole`, `Ref` and `Raw` go inside. A space
follows a control word when the next text could continue its name. Loops and conditions are plain Python:

```python
class Rating(Command):
    '''Says which level it has.'''
    level: Level                                   # a Choice whose members are macros: \lvLow, \lvHigh

    def body(self):
        for member in Level:                       # one branch per member, chosen when TeX expands the call
            yield Seq(Cs("ifx"), Hole("level"), member.value, Group(Lit(member.name)), Cs("fi"))
# \ifx #1\lvLow{LOW}\fi
# \ifx #1\lvHigh{HIGH}\fi
```

texmodel writes this TeX and never reads TeX it did not write. The pieces are lines in the package's `Whitespace` policy;
a `Ref` inside a `Group` still makes its package a requirement.

### expl3 and library blocks

expl3 is a syntax mode and a source kind, not a typed language: texmodel has no vocabulary of `\fp_` or `\seq_` functions, and the
compile tells you when one is wrong. `Syntax` (`texmodel.body`) is `LATEX2E` (the default) or `EXPL3`. A body is in one syntax
(`TM-M031` if its pieces differ): give each `TexRaw`, `TemplateRef` and `Cs` that is expl3 `syntax=Syntax.EXPL3`. The generated
definition is then wrapped in `\ExplSyntaxOn` / `\ExplSyntaxOff`, no `%` is added at line ends (a piece's `Whitespace` is ignored),
and a `Lit` or a text argument of a `Ref` writes `~` for a space. A component whose `cs` has `_` or `:` says
`syntax = Syntax.EXPL3`.

`Package.library(name, source, syntax=Syntax.EXPL3)` carries TeX into the `.sty` verbatim: dedented, blank edges removed, no `%`
added, `#1` and `##1` as written, in registration order among the package's items, under a provenance comment. Its only static
checks are balanced braces (`TM-M011`) and no `\ExplSyntaxOn` / `\ExplSyntaxOff` inside an `EXPL3` block (`TM-M034`). Every
line of the block has its name as its plan path, and a name is used once (`TM-M007`). `source` is a string or a `TemplateRef`.

```python
sizing = pkg.library("sizing", r"""
    \fp_new:N \l__cd_size_fp
    \newcommand{\cdFitSize}[2]{ \fp_set:Nn \l__cd_size_fp { min ( 14 , max ( 8 , 12 * #2 / #1 ) ) } }
""", syntax=Syntax.EXPL3)

@pkg.command
class FitSize(Command):
    '''Work out the title size.'''
    defined_by = sizing               # declared and callable (FitSize.call(...)), but no \newcommand is rendered
    natural: Raw
    available: Raw
```

A component with `defined_by` has no body (`TM-M032`) and its block belongs to the same package (`TM-M033`). `texmodel check`
reads each block (`Package.check_parts()`, no TeX needed) and reports a declared component the block does not define with that
signature (`TM-C010`, `TM-C011`), a public `<prefix>Name` the block defines that nothing declares (`TM-C012`), and a name
defined twice (`TM-C013`; generation itself refuses it, `TM-P012`). The reading is regex-level (`\newcommand`, `\providecommand`,
`\DeclareRobustCommand`, `\newenvironment`, the xparse family, `\newlength`, `\newtoggle`, `\newif`, `\definecolor`) and
skips an expl3 block. `texmodel.package.declared(text)` is the set of control sequences those forms declare in a text (no `\def`, `\let` or expl3 definers, which count as missing). A flag, toggle, length, colour or text setting a block defines is a `Value` with `defined_by` (no default;
`cs = "..."` gives the whole control sequence, `colour_name` the colour's name). For the
rest, whether TeX really defines it, with that many arguments, is checked by compiling: `texmodel_build.testkit.check_library(compiler, pkg)`
builds `pkg.test_document(...)` with `export_probes(pkg)` (it writes `texmodel:probe:def.<cs>=yes|no` and
`arity.<cs>=<n>` for each such component), compiles it, and returns `TM-C010` for a name the block does not define and
`TM-C011` for another number of arguments (`?` is checked for existence only). The arity is the number of `#` in the macro's
`\meaning`, so a command defined with `\NewDocumentCommand` or with an optional first argument reports `0`, which
`check_exports` flags as `TM-C011` when more arguments are declared. A block that TeX refuses fails the compile with the block's name as the diagnostic's `path`.

The PDF Info strings need no expl3 in a document: `PdfInfo(Title="...", Author="...")` in `before_package` or `after_package`
writes each value PDF-escaped through `\csname pdfmanagement_add:nnn\endcsname`, and needs `RequireMetadata` in `before_class`
(`TM-C009`). A key is letters only (`TM-M035`).

Give it the text as it is; do not trim, balance or escape it first. Unbalanced `(` and `)`, `\`, `#`, `%`, `&`, `$`, braces,
a trailing or doubled space, newlines and non-ASCII (é, —, CJK, emoji) reach the PDF Info dictionary unchanged (a PDF text string
is PDFDocEncoding or UTF-16BE: non-ASCII is written as UTF-16BE). A compile test reads a corpus of such values back from the PDF.
`PdfString` (`texmodel.types.pdf_escape`) is the same escaping for a string you write yourself.

### Parts filled from a model

A package that starts from TeX you already have is a list of parts: `pkg.library(name, TemplateRef("brand.tex"), fill=model)`.
`fill` is a mapping, a dataclass or a pydantic model, and the text's `<<name>>` holes (`<<a.b>>` into a nested model) are
filled by type: `str` is escaped, `Raw` passes through, a `Length`, a colour model, a number or a flag is written as it is.
A hole the model has no field for is an error (`TM-M041`), as is a value of another type (`TM-M040`); a model may hold more
than the part uses. Without `fill` a block is carried exactly as it is. Components with `defined_by` then give decks typed
calls to what the parts define. [The cookbook](docs/cookbook.md) has a worked example.

### Arguments: slots, value types and key lists

A field is an argument; its type says what it holds and `arg(...)` says how it is written (`texmodel.interface`).
Without `arg()`, a required field is `{...}` and an optional one (a default) is TeX's one optional argument, `[...]`,
written first. With `arg()` the slot keeps its declaration order, so any signature can be stated:

```python
from texmodel.interface import PAREN, SQUARE, Gap, SlotGroup, Star, arg

class MakeBox(Command):                       # \makebox[3cm][c]{x}
    cs = "makebox"
    width: Length | None = arg(SQUARE, default=None, fill=Gap.REFUSE)   # `[c]` alone is not valid: refused
    align: BoxAlign | None = arg(SQUARE, default=None)
    text: Raw

class Section(Command):                       # \section*[short]{long}
    cs = "section"
    starred: Star = arg(default=False)        # a token: `*`
    short: Text | None = arg(SQUARE, default=None)
    title: Text

class Put(Command):                           # \put(1,2){x}
    cs = "put"
    at: tuple[int, int] = arg(PAREN)          # a tuple, written `1,2` (`sep=` changes the comma)
    text: Raw
```

- **Slots.** `{}` `[]` `()` `<>` or your own `Delimiter`; a `Star` or other token; a slot left out is not written, and an
  optional slot left out before a later optional one writes `fill=` (say `""` for empty brackets) or is refused
  (`Gap.REFUSE`); declaring two optionals without saying which is `TM-M037`. A `SlotGroup` is written together or not at all.
  Optional and token fields are keyword-only in Python wherever they stand. Write an optional field with `arg(default=...)`
  (`label: Text | None = arg(default=None)`): a type checker then reads it as keyword-only and accepts a required field after
  it, where a plain `= None` is reported as a field-order error although it runs.
- **Value types.** `Text` (escaped), `PdfString`, `Raw`, `Length` (`Length("2mm")`, or `Length.expr(r"\linewidth")` for a TeX
  expression), a colour model (`CMYK`, `RGB`, `Gray`) or a `ColourName` (`blue!50`), `int`, `float`, `bool` (`true`/`false`),
  a `Choice`, a tuple, `NamedTuple`, dataclass or model of those, a `list`, and a `KeyVals`. A wrong value is a violation
  with the field's path.
- **Definitions.** A signature `\newcommand` can define keeps it. Several optional arguments, other delimiters or a token
  are defined with `\NewDocumentCommand` / `\NewDocumentEnvironment` (xparse, in the LaTeX kernel; the arguments are
  `#1`... in TeX order, an optional one left out is empty and a token is `\BooleanTrue` / `\BooleanFalse`). Stubs
  and `check_interface` follow: `check_interface` reads `\NewDocumentCommand` family definitions as xparse letters.

A key list (`\adjustbox{max width=\linewidth, center}{...}`) is a `KeyVals`, a frozen pydantic model: its field types say
how each item is written, and its `KeyRules` say how the library reads it.

```python
from texmodel.interface import Flag, Item, OptionalValue, Switch
from texmodel.keys import PGFKEYS
from texmodel.keyvals import KeyVals, key

class AdjustOptions(KeyVals, rules=PGFKEYS):
    max_width: Length | None = key("max width")       # max width=3cm
    center: Flag = False                              # center
    clip: Switch | None = None                        # clip=true / clip=false
    valign: VAlign | None = None                      # valign=t   (a Choice)
    rounded: OptionalValue[Length] | None = key("rounded corners")   # rounded corners  /  rounded corners=2pt
    style: Inner | None = key("every node/.style")    # every node/.style={draw=red}   (another KeyVals)
    tags: list[Text] | None = None                    # tags=a,tags=b   (a list repeats the key)
    extra: Item[Raw] | None = None                    # anything else, as written (an Item has no key)

AdjustBox(AdjustOptions(max_width=Length.expr(r"\linewidth"), center=True), Raw("x"))
```

Items are written in declaration order and unset ones are left out. A `Text` value the library would split (`,` `=` `]`) is
put in braces, and `exclusive` / `requires` on the class refuse combinations. Presets in `texmodel.keys` (`PGFKEYS`,
`XKEYVAL`, `KVOPTIONS`, `L3KEYS`, `KEYVAL`) hold what a library does; `dataclasses.replace(PGFKEYS, booleans=("on", "off"))`
makes another. They were measured, not assumed: `tests/test_texmodel/test_interface_tex.py` passes awkward values through
pgfkeys, xkeyval, keyval and l3keys. All four read `,` `=` `]` safely when braced and strip a space at either end of a
value, which `{{ a }}` keeps in three of them (`l3keys` trims whatever it is given, `KeyRules.edge_spaces`). `KVOPTIONS` is `XKEYVAL` without nesting and was not measured.

### Components from data

A program that decides names at run time declares them with `pkg.make_command` and `pkg.make_value`; each builds the class and
registers it, as the decorators do:

```python
name = pkg.make_command("Name", "the subject's name", fields={"name": (Raw, field(doc="the name"))}, body=r"\bb@title{#name}")
cut = pkg.make_value("TechCut", Colour, "the cut line", default=CMYK(0, 0.4, 1, 0), colour_name="bbTechCut")
```

`fields` maps a name to `(hint, field(...))` in TeX order, as pydantic's `create_model` does. Declaring the same data again
returns the class made first, so several series can share a macro; other data under the same name is `TM-M007`. `module`
(default: the package's name) is the module shown in messages.

### What is public on a component

An attribute without a leading underscore is public and read-only: on a component `cs`, `syntax`, `defined_by`, `meta`
and (an `Environment`'s) `children`; on a `Value` also `default`, `colour_name` and `needs_packages`. Read them; do not assign
them after the class is registered. `meta` is the mapping given in the class body (`meta = {"audience": "deck"}`), written to
the schema as `x-audience`. Anything starting with `_`, including every `__tm_*` attribute, is internal and may change in any
release. `describe(cls)` (`texmodel.components`) reports a registered command, environment or value as a frozen `Description`
(`category`, `name`, `cs`, `doc`, `arguments` of `ArgumentInfo(name, optional, doc)`, a value's `python` type, `default` and
`colour_name`); an unregistered class is `TM-M019`. `control_name(value)` and `Value.declared_default()` are the narrower ways.

A command, an environment and a `Passthrough` are frozen pydantic models. Building one in Python checks nothing beyond the
signature (`node.violations()` does, all at once); `node.model_fields_set` is the set of fields the caller passed,
positionally or by keyword, a default given included (an environment's `content` is always in it). Equality and hashing
compare the fields, not that set. A field cannot be named like an attribute every component has (`copy`, `json`, `render`,
anything starting `model_`): `TM-M045`.

### Standard libraries

`texmodel.std` has a header for each TeX library a deck loads: `latex` (the kernel), `graphicx`, `xcolor`, `geometry`,
`etoolbox`, `eso_pic`, `microtype`, `hyphenat`, `anyfontsize`, `calc`, `pdfrender`, `enumitem`, `adjustbox`, `tikz`,
`tcolorbox`, `fontspec`. A header is an adopted package with no prefix whose components name their TeX command with `cs`:

```python
class IncludeGraphics(Command):
    r"""Place a picture: `\includegraphics[width=3cm]{a.png}`."""
    cs = "includegraphics"            # the TeX name, stated outright; without `cs` it is prefix + class name
    path: Raw
    options: IncludeGraphicsOptions | None = None    # a KeyVals: TeX's one optional argument, written first
```

A body that calls one (`IncludeGraphics.call(Hole("path"), options=IncludeGraphicsOptions(width=Length.expr(r"\linewidth")))`) makes the generated `.sty`
load the package; the kernel header (`builtin=True`) never does. A library whose commands no body calls, or that takes
options, is loaded with `pkg.require(microtype, options=["protrusion=true"])`: `\RequirePackage[protrusion=true]{microtype}`,
in that order, before the packages the bodies need. `tests/test_std` compiles a call of every declared name against the
reference image, so a header that names a command TeX does not have fails, with the path of the call. `adjustbox`, `graphicx`,
`geometry`, `tcolorbox` and `tikz` type their key lists, `calc` is a typed expression language (`dimen(Length("2cm")) * real(0.5) + widthof("abc")`, with `maxof`, `minof`, `ratio`, `glue`, `integer`, `counter_value`), and the kernel types `\vspace*`, `\makebox`, `\raisebox` and
the sectioning commands; a library's own syntax (TikZ paths such as `\draw (0,0) -- (1,1);`) is written as `Passthrough`
or `Raw`.

### A package that is already written in TeX

When the `.sty` is hand-written, declare what it defines instead of generating it: `adopted=True` (M9). The components
have no body, `build` writes no file, documents are still checked and escaped, and `texmodel check` compares each
declaration with the TeX it names (`\newcommand`, `\providecommand` and `\newenvironment` are read; a name defined any
other way counts as missing):

```python
pkg = Package("card-deck", prefix="cd", adopted=True)     # the package name is the hand-written one

@pkg.command
class TalkAboutMe(Command):
    """A question, with an optional answer."""
    question: Text
    answer: Text | None = None            # declared [2][]: \newcommand{\cdTalkAboutMe}[2][]{...}

@pkg.command
class DeckName(Command):                   # no fields: a setting the deck sets with \renewcommand
    """The deck name printed on every card."""
```

```toml
[tool.texmodel]
package = "deck.model:pkg"
sources = ["res/brand/*.sty"]            # globs, relative to pyproject.toml
```

```zsh
texmodel check     # TM-C010: declared, not defined; TM-C011: defined with another signature
```

`Package.document(..., preamble=PreambleSlots(before_class=, before_package=, after_package=))` places `Raw` TeX where the
document needs it: `before_class` for `\DocumentMetadata`, `before_package` for `\input@path`, `after_package` for
`\graphicspath` and per-document `\renewcommand`s. A public name of the package used there (`\cdSafeInset`) that no
component declares is refused with its path (`TM-M015`, `preamble.after_package[0]`). Typed entries render to one `Raw` and know
their slot: `PassOption("xcolor", "table")`, `InputPath("res/")` (`before_package`), `InputIfExists("deck-variant")` (`\InputIfFileExists{deck-variant}{}{}`, `before_package` or `after_package`), `GraphicsPath("images/")` (`after_package`,
the current directory first unless `include_cwd=False`) and `RequireMetadata(lang="en-GB")` (`before_class`); one in another
slot is `TM-C008`. `tests/consumers/card_deck/` is a
complete example: a hand-written package, the generator it replaces and a 3-card deck.

### A text setting

```python
@pkg.value
class DeckName(Value[Text]):
    """The deck name printed on every card."""
    default = "Untitled"          # an adopted package may leave it out: the hand-written TeX has it

pkg.document(card, settings=[DeckName("R&D")])    # \renewcommand{\acDeckName}{R\&D}, after \usepackage
```

A generated package defines `\newcommand{\acDeckName}{Untitled}`; for an adopted one `texmodel check` expects the hand-written
package to define the macro with no arguments. Every setting, of any type, is written right after `\usepackage`, in the order given, before `after_package`.
`texmodel.package.setting_line(value)` is the line written for one setting.

A `Value[Raw]` is the same for a setting that is TeX (`\newcommand{\acFooter}{\textit{draft}}`, renewed by `settings=[Footer(Raw(...))]`).
A `PdfString` field holds text for the inside of a PDF literal string you write yourself (`\pdfextension info{/Subject (#text)}`):
it is written as `\detokenize{...}` with `( ) \` and every TeX special as an octal escape (`\050`), and text with a non-ASCII
character as UTF-16BE, so a parenthesis cannot cut the string short, `%` or `_` cannot break the TeX, and a reader gets the
text back. It is not for `\hypersetup{pdftitle=...}`: hyperref escapes its own input.

### Layout that is not a component

```python
class Page(Environment):
    '''A page.'''
    children = [Name, Anywhere(Heading), Fact.times(2, 3), Passthrough.times.any()]

Page(Name("Rex"), Heading("Facts"), Fact("a"), Passthrough(Raw(r"\vspace{1mm}")), Fact("b"))
```

`Anywhere(Heading)` allows zero or more of that component anywhere among the other children; it is not counted against the
ordered terms and the kind cannot also be an ordered term (`TM-M029`). `Passthrough(Raw(...))` writes its TeX as it is and is
accepted only where a grammar lists it.

### A closed set of values

A `Choice` is an enum whose members carry their TeX: a `Raw` passes through, a `str` is escaped. Use it as a field type
(optionally `| None`); data names a member by its name.

```python
@enum.unique
class SlotLabel(Choice):
    SOUND = Raw(r"\deckParamSound")
    WHERE = Raw(r"\deckParamWhere")

@pkg.command
class LabelledSlot(Command):
    """A fact with a label."""
    label: SlotLabel
    text: Text

LabelledSlot(SlotLabel.SOUND, "A soft woof.")      # \cdLabelledSlot{\deckParamSound}{A soft woof.}
```

### A document from data

`texmodel.spec` loads a document from plain data (what TOML or JSON gives), using pydantic: a child names its component with
`"type"`, an environment's children are its `content`, a `Raw` field takes a string.

```python
from texmodel.spec import from_dict, json_schema, to_dict

card = from_dict(Card, {"content": [
    {"type": "CardFront", "content": [{"type": "CardImage", "path": "a.jpg"}]},
    {"type": "CardBack", "content": [{"type": "Name", "text": "Fox"}, {"type": "LeadFact", "text": "..."}]},
]})
card.violations()      # the grammar (counts, order) is checked here, as for any tree
to_dict(card)        # the same shape back
json_schema(Card)    # JSON Schema of what from_dict accepts
```

Everything wrong comes at once as an `ExceptionGroup` of `ValidationError` (`TM-C020`), each with a path such as
`Card/CardBack[1]/LeadFact[2].text`. `to_dict` writes the fields a node was given (`model_fields_set`), so data loaded and
written back keeps its keys, and a default the author left out stays out.

### A schema for the package's data

`texmodel schema` writes `json_schema(pkg)` to `[tool.texmodel] schema_output`: one JSON Schema with a `$defs` entry for every
command and environment (a child is told apart by its `"type"` constant) and `Value.<Name>` for every value, for editors and
validators of the TOML or JSON that `from_dict` reads. A renamed field keeps loading under its old key:

```python
class Fact(Command):
    '''One fact.'''
    text: Text = field(renamed_from="body")       # {"body": "..."} loads; to_dict writes "text"; the schema has x-renamed-from
```

### Checking committed documents

```toml
[tool.texmodel.documents]
"deck.tex" = "deck.build:plan()"       # committed file = pointer to a Plan (or a str) the model renders
```

`texmodel check` renders each pointer from today's model and compares it with the committed file, like `terraform plan`:
for a `Plan` every difference names the component that writes the line (`changed  deck.tex Card[1]/CardBack[1]/LabelledSlot[3]: ...`),
so a hand edit and a stale render read the same; a `str` is compared whole. Exit 1 on any difference; `texmodel render` with no
pointer rewrites every configured document.

### Comments

```python
from texmodel.body import Comment

class CardHeader(Comment):
    """The audit block above a card."""
    template = """
        Card: #name
          id: #id
    """
    name: str
    id: str

pkg.document(CardHeader("Red Fox", "11111111-aaaa"), Card(...))     # % Card: Red Fox / %   id: 11111111-aaaa
```

Every line of a `Comment` is prefixed `% `, so a value cannot leave it; nothing is escaped (`##` is a `#` in a template). It
is a body piece (`yield Comment("why this is 3mm")`) and a document node: a child of an environment or a top-level node, and
transparent to the grammar (not counted, never listed, paths keep the real index: `Card[3]/CardHeader[0]`). It needs no
package registration. `plan.edits(text, ignore_comments=True)` skips lines that are comments on both sides. In data a
child may be a `Comment` (`"type": "Comment"`) or one of the classes its environment's package lists,
`Package("card-deck", prefix="cd", comments=[CardHeader])`: `from_dict` and `json_schema` know it (`"type": "CardHeader"`).

### Testing generated code with stubs

A component's body decides what it passes on to other components. `expand(node, stubs=[Fact])` (`texmodel.testing`) walks the
bodies with the node's values and returns the body text and a `Call` for every stubbed component, in order, with no TeX:

```python
from texmodel.testing import Call, expand

section = Section(Entry("First"), Entry("R&D 50%"), title="Notes")
assert [c for c in expand(section, stubs=[Fact]) if isinstance(c, Call)] == [
    Call("bkFact", ("First",)), Call("bkFact", (r"R\&D 50\%",))]
```

The TeX tier checks the real macros do the same: `pkg.test_document(section, stub=[Fact])` loads the real packages and replaces
each stub with a macro that writes `texmodel:probe:callN=bkFact{...}` to the log; `texmodel_build.testkit.run_probes(compiler,
tex, files={"base-kit.sty": ...})` compiles it and returns the probes, which `Call.parse` reads. Arguments are shown as
`\detokenize` shows them (a space after each control word), so both tiers agree. Layout is not covered: this tests what a
component passes on, not how it looks.

### Where a line came from

`pkg.plan(...)` takes the arguments of `pkg.document(...)` and returns a `Plan`: every output line with the path of what wrote it
(`Card[1]/CardBack[1]/LabelledSlot[3]`, `preamble.after_package[0]`). `plan.text` is the document. Store `plan.to_json()` beside
the committed file; `Plan.from_json(saved).edits(text)` then names each hand edit by the path it had when it was written, even
if the model has changed since, and `plan.path_of(39)` names the component behind a log's `input line 39`. `Compiler.compile(src, out, plan=plan)` does
that for every diagnostic in the source: `diagnostic.path` is the component behind its line; `plans={"acme.sty": pkg.render_plan()}` does the
same for diagnostics in other files, by file name.

`texmodel.bundle` copies a manifest of files and refuses if any is missing (`stale` compares bytes, not timestamps);
`texmodel.drift` is what `check` uses; `texmodel.pointer` resolves `module:object` pointers (a package, a document, a `Plan`).

## texmodel-build

```zsh
texmodel-build doctor                       # tools on this machine, and what the configured image has
texmodel-build doctor --sty 'res/*.sty'     # which files those packages load that the toolchain lacks (kpsewhich), with a tlmgr line; exit 3
texmodel-build compile doc.tex              # exit 0 ok, 1 errors in the document, 3 tool or image missing
texmodel-build compile doc.tex --json --epoch 1700000000 --root generated
texmodel-build compile deck.tex --plan "deck.build:plan()"   # diagnostics name the component: [Card[1]/CardBack[1]/Name[0]]
texmodel-build build -j 4                   # every [tool.texmodel-build.targets.*]
texmodel-build verify out/*.pdf             # verifier plugins; anything unconfirmable fails
```

```toml
[tool.texmodel-build]
image = "releaseart/lualatex-python:latest"   # runs `docker run` over it; omit to run on this machine
```

- The compile log becomes typed diagnostics with stable codes: undefined control sequences (`TM-X010`), missing glyphs
  (`TM-X011`), overfull boxes (`TM-X012`), missing files (`TM-X013`), package errors (`TM-X014`), undefined references
  (`TM-X018`), package warnings with their continuation lines (`TM-X019`, how a hand-written package says a card does
  not fit), non-convergence with the `.aux` entries that keep moving (`TM-X030`), and a fallback so no failure is silent.
- A package's "does not fit" warning becomes a typed `Overset` (`TM-X031`, an error: item, needs, has, over, in pt) when a
  rule says how to read it; the warning is kept too. A package that prints `texmodel:probe:fit.<item>=<needs>/<has>` needs
  no rule. Lengths take `pt`, `mm`, `cm`, `in` (a bare number is pt); an item that fits gives none.

  ```toml
  [tool.texmodel-build.measures.card-fit]
  package = "card-deck"
  pattern = "Card '(?P<item>[^']+)' does not fit. Its body needs (?P<needs>\\S+) and the card has (?P<has>\\S+)"
  ```
- Reproducibility is the image's job (`--epoch` pins `SOURCE_DATE_EPOCH`); there is no sandbox or cache here.
- `texmodel-build verify` runs plugins from the `texmodel_build.verifiers` entry-point group. `pip install
  'texmodel[proof-pdf]'` adds [proof-pdf](https://github.com/release-art/proofpress). A verifier that cannot run, a
  file that cannot be opened and a profile that selects nothing are failures; the only excuse is a declared `exempt` glob.
- The image must contain `latexmk` (`releaseart/lualatex-python` has it since proofpress v0.3.4); `doctor` reports it if not.

## Where it is going

Open work is in [the plan](docs/texmodel-plan.md) (§19, §21a) and [the roadmap](docs/briefs/roadmap.md).

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). `bin/autoformat.sh` runs ruff, strict pyright and import-linter over both packages;
`bin/test.sh` runs pytest with a 100% coverage gate. The container compile suite is `pytest -m tex`; it skips without an
image that has `latexmk`, and `TEXMODEL_REQUIRE_TEX=1` turns that skip into a failure (`TEXMODEL_TEST_IMAGE` sets the image).
`bin/test-image.sh` builds `texmodel-test` from `docker/test/Dockerfile`: the published reference image plus the few TeX
packages the suite needs that it does not carry yet (`TEXMODEL_TEST_IMAGE=texmodel-test pdm run pytest -m tex`); CI uses it.

Public API is the top-level modules of each package; everything under `_internal` may change. Report vulnerabilities as
described in [SECURITY.md](SECURITY.md).

## Licence

[MIT](LICENSE). The reference images carry their own licences (Ghostscript is AGPL); `texmodel-build` runs them as a
separate process and ships none of their code.
