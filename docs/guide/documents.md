# Documents

A document is a tree of component objects. `pkg.document(...)` renders it. The blocks on this page run in order, as one
module.

```python
from texmodel.components import Command, Environment, field
from texmodel.package import Package, PreambleSlots
from texmodel.preamble import GraphicsPath, InputIfExists, InputPath, PassOption, PdfInfo, RequireMetadata
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import Raw, Text

pkg = Package("deck", prefix="dk")


@pkg.command
class Name(Command):
    """The name."""

    text: Text = field(renamed_from="body")
    body = r"\par\textbf{#text}\par"


@pkg.command
class Fact(Command):
    """A fact."""

    text: Text
    body = r"\par #text\par"


@pkg.environment
class Card(Environment):
    """A card."""

    children = [Name, Fact.times.at_least_one()]
    begin = r"\begin{minipage}{\linewidth}"
    end = r"\end{minipage}"


card = Card(Name("Rex"), Fact("Friendly & loyal."))
tex = pkg.document(card, options=["a4paper"])
assert r"\dkFact{Friendly \& loyal.}" in tex
```

`Text` fields are escaped; a `Raw` field passes TeX through. `card.validate()` lists every broken rule at once, each with a
code and a path such as `Card/Fact[2].text`; `pkg.document` raises the same list as an `ExceptionGroup` of `ValidationError`.

## The preamble

`pkg.document(..., preamble=PreambleSlots(before_class=, before_package=, after_package=))` places TeX where the document
needs it:

| Slot | For |
|---|---|
| `before_class` | `\DocumentMetadata` |
| `before_package` | `\input@path`, options passed to packages |
| `after_package` | `\graphicspath`, PDF info, per-document `\renewcommand`s |

Typed entries render to one `Raw` and know their slot. One in another slot is `TM-C008`.

| Entry | Slot | Writes |
|---|---|---|
| `RequireMetadata(lang="en-GB")` | `before_class` | `\DocumentMetadata{lang=en-GB}` |
| `PassOption("xcolor", "table")` | `before_class`, `before_package` | `\PassOptionsToPackage{table}{xcolor}` |
| `InputPath("res/")` | `before_package` | `\input@path` |
| `InputIfExists("deck-variant")` | `before_package`, `after_package` | `\InputIfFileExists{deck-variant}{}{}` |
| `GraphicsPath("images/")` | `after_package` | `\graphicspath{{}{images/}}` (current directory first unless `include_cwd=False`) |
| `PdfInfo(Title="Rex")` | `before_package`, `after_package` | PDF Info entries, below |

```python
slots = PreambleSlots(
    before_class=(RequireMetadata(lang="en-GB"),),
    before_package=(InputPath("res/"), PassOption("xcolor", "table"), InputIfExists("deck-options")),
    after_package=(GraphicsPath("images/"), PdfInfo(Title="Rex (the fox)", Subject="50% & more")),
)
tex = pkg.document(card, preamble=slots)
assert tex.index(r"\DocumentMetadata") < tex.index(r"\documentclass") < tex.index(r"\usepackage{deck}")
```

Raw TeX is also accepted in a slot. A public name of the package used there that no component declares is refused with its
path (`TM-M015`, `preamble.after_package[0]`).

### PdfInfo

`PdfInfo` writes each value PDF-escaped through `\pdfmanagement_add:nnn`. It needs `RequireMetadata` in `before_class`
(`TM-C009`), and a key is letters only (`TM-M035`). Give it the text as it is; do not trim, balance or escape it first.
Unbalanced `(` and `)`, `\`, `#`, `%`, `&`, `$`, braces, a trailing or doubled space, newlines and non-ASCII (é, —, CJK, emoji)
reach the PDF Info dictionary unchanged. A compile test reads a corpus of such values back from the PDF.

## A document from data

`texmodel.spec` loads a document from plain data (what TOML or JSON gives), using pydantic. A child names its component with
`"type"`, an environment's children are its `content`, and a `Raw` field takes a string.

```python
data = {"content": [{"type": "Name", "text": "Fox"}, {"type": "Fact", "text": "Quick."}]}
loaded = from_dict(Card, data)
assert loaded.validate() == []                 # the grammar (counts, order) is checked here, as for any tree
assert to_dict(loaded) == {"type": "Card", "content": [{"type": "Name", "text": "Fox"}, {"type": "Fact", "text": "Quick."}]}
assert "$defs" in json_schema(Card)
```

Everything wrong comes at once as an `ExceptionGroup` of `ValidationError` (`TM-C020`), each with a path such as
`Card/Fact[2].text`.

A renamed field keeps loading under its old key. `text: Text = field(renamed_from="body")` loads `{"body": "..."}`, writes
`"text"`, and the schema records `x-renamed-from`:

```python
assert from_dict(Name, {"body": "Fox"}).text == "Fox"
```

`field(doc=, meta=)` and a class-level `meta = {"audience": "deck"}` put a description and `x-` keys in the schema.

## A schema for the data

`texmodel schema` writes `json_schema(pkg)` to `[tool.texmodel] schema_output`: one JSON Schema with a `$defs` entry for
every command and environment (a child is told apart by its `"type"` constant) and `Value.<Name>` for every value. Use it
for editor support and validators of the TOML or JSON that `from_dict` reads. It describes one package's data, so it needs a
single `package` in the configuration.

## Where a line came from

`pkg.plan(...)` takes the arguments of `pkg.document(...)` and returns a `Plan`: every output line with the path of what
wrote it (`Card[1]/Fact[0]`, `preamble.after_package[0]`).

```python
plan = pkg.plan(card, preamble=slots)
assert plan.text.startswith("% deck document")
assert plan.lines[0].path == "header"
```

- `plan.text` is the document. Store `plan.to_json()` beside the committed file.
- `Plan.from_json(saved).edits(text)` names each hand edit by the path it had when it was written, even if the model has
  changed since. `plan.edits(text, ignore_comments=True)` skips lines that are comments on both sides.
- `plan.path_of(39)` names the component behind a log's `input line 39`.
- `Compiler.compile(src, out, plan=plan)` does that for every diagnostic in the source: `diagnostic.path` is the component
  behind its line. `plans={"deck.sty": pkg.render_plan()}` does the same for diagnostics in other files, by file name.
