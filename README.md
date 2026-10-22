# texmodel

[![CI](https://github.com/release-art/texmodel/actions/workflows/ci.yml/badge.svg)](https://github.com/release-art/texmodel/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Declare a LaTeX document family once in Python types; get plain, readable, git-trackable `.sty` source out of it. The output
is ordinary TeX: commit it, diff it, compile it with whatever LaTeX setup you already have.

> **Status: pre-alpha, not on PyPI.** One component kind (`Command`) renders to a `.sty` today. Environments, values,
> `Doc` trees, schema export and migrations are designed (see [the plan](docs/texmodel-plan.md)) but not built.

This repository holds two packages, released in lockstep:

| Package | What it is |
|---|---|
| **`texmodel`** (`src/`) | The library: declare components, render deterministic TeX, check that committed output is current. No TeX needed, no processes spawned. |
| **`texmodel-build`** (`harness/`) | Optional: a thin `latexmk` driver with typed log diagnostics, and verifier plugins for built PDFs. Use it if you want compile results as data; your own `latexmk` or image works just as well. |

## texmodel

```python
# acme_cards/__init__.py
from texmodel.body import TemplateRef
from texmodel.components import Command, Environment, Value
from texmodel.package import Package
from texmodel.types import CMYK, Bool, Colour, Length, Text

pkg = Package("acme-cards", prefix="ac", version="1.4.0", date="2026/10/21")

@pkg.value
class FactGap(Value[Length]):
    """Space under each fact."""
    default = Length("2mm")

@pkg.value
class Ink(Value[Colour]):
    """The text colour."""
    default = CMYK(0, 0, 0, 0.95)

@pkg.value
class Compact(Value[Bool]):
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
CardBack(Fact("x")).validate()   # [Violation(TM-C002 ...), Violation(TM-C001 path='CardBack/Fact[0]' ...)]
```

```toml
# pyproject.toml
[tool.texmodel]
prefix = "ac"
package = "acme_cards:pkg"
output = "generated"
```

A pointer (`package =`, and the argument of `texmodel render`) is `dotted.module:object`, `dotted.module:namespace.object`
(attributes are followed) or `dotted.module:getter()` (called with no arguments; its result is used):

```toml
package = "acme_cards.decks:Decks.birds"      # or "acme_cards.decks:make_package()"
```

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

### Generating a body

A body can also be built from pieces that are well-formed by construction, so a generator cannot write an unbalanced brace or
a bad control word. `Group(...)` is `{...}`, `Seq(...)` the same without braces, `Cs("par")` a control word (letters and `@`
only, else `TM-M027`), `Lit("50% & co")` text escaped as a `Text` field is, and `Hole`, `Ref` and `Raw` go inside. A space
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
prefix = "bb"
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
their slot: `PassOption("xcolor", "table")`, `InputPath("res/")` (`before_package`), `GraphicsPath("images/")` (`after_package`,
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
package to define the macro with no arguments. Length, colour and flag settings are written in the document body as before.

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
card.validate()      # the grammar (counts, order) is checked here, as for any tree
to_dict(card)        # the same shape back
json_schema(Card)    # JSON Schema of what from_dict accepts
```

Everything wrong comes at once as an `ExceptionGroup` of `ValidationError` (`TM-C020`), each with a path such as
`Card/CardBack[1]/LeadFact[2].text`.

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
package registration. `plan.edits(text, ignore_comments=True)` skips lines that are comments on both sides;
`from_dict(cls, data, comments=[CardHeader])` and `json_schema(cls, comments=[...])` know it as a child (`"type": "CardHeader"`).

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
that for every diagnostic in the source: `diagnostic.path` is the component behind its line.

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
  'texmodel-build[proof-pdf]'` adds [proof-pdf](https://github.com/release-art/proofpress). A verifier that cannot run, a
  file that cannot be opened and a profile that selects nothing are failures; the only excuse is a declared `exempt` glob.
- The image must contain `latexmk` (`releaseart/lualatex-python` has it since proofpress v0.3.4); `doctor` reports it if not.

## Where it is going

| Step | Contents | State |
|---|---|---|
| A | build harness: compile, typed diagnostics, verifier plugins, drift, bundle | built |
| B | rendering core: types, `Command`/`Environment`/`Value`, `.sty`, `Doc` trees, schema | `Command` → `.sty` and `build`/`check` done |
| C | migrations, adopting hand-written TeX, a standard library, docs, 1.0 | after B |

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). `bin/autoformat.sh` runs ruff, strict pyright and import-linter over both packages;
`bin/test.sh` runs pytest with a 100% coverage gate. The container compile suite is `pytest -m tex`; it skips without an
image that has `latexmk`, and `TEXMODEL_REQUIRE_TEX=1` turns that skip into a failure (`TEXMODEL_TEST_IMAGE` sets the image).

Public API is the top-level modules of each package; everything under `_internal` may change. Report vulnerabilities as
described in [SECURITY.md](SECURITY.md).

## Licence

[MIT](LICENSE). The reference images carry their own licences (Ghostscript is AGPL); `texmodel-build` runs them as a
separate process and ships none of their code.
