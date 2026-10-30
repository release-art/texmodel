# Documents

A document is a tree of component objects. `pkg.document(...)` renders it. The blocks on this page run in order, as one
module.

```python
from texmodel.components import Command, Environment, Value, field
from texmodel.document import Document
from texmodel.package import Package
from texmodel.preamble import PreambleSlots
from texmodel.preamble import GraphicsPath, InputIfExists, InputPath, PassOption, PdfInfo, RequireMetadata
from texmodel.spec import from_dict, json_schema, to_dict
from texmodel.types import Length, Raw, Text

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


@pkg.value
class Gap(Value[Length]):
    """The gap between facts."""

    default = Length("2mm")


card = Card(Name(text="Rex"), Fact(text="Friendly & loyal."))
tex = pkg.document(card)
assert r"\dkFact{Friendly \& loyal.}" in tex
```

`Text` fields are escaped; a `Raw` field passes TeX through. `card.violations()` lists every broken rule at once, each with a
code and a path such as `Card/Fact[2].text`; `pkg.document` raises the same list as an `ExceptionGroup` of `ValidationError`.

## A package built on another

`Package("acme-series", prefix="as", base=brand)` specializes `brand`: its `.sty` loads the base first, and a document of
the series may hold the base's nodes and settings. `series.visible` is every class the series can name and
`series.value_named("Gap")` finds a value (or `None`); a name the series declares itself replaces the base's, in data, the
schema and the lookup. `from_dict(series, data)` reads the base's names too.

```python
brand = Package("acme-brand", prefix="ac")


@brand.value
class Pad(Value[Length]):
    """The padding."""

    default = Length("1mm")


series = Package("acme-series", prefix="as", base=brand)
assert series.value_named("Pad") is Pad
assert r"\RequirePackage{acme-brand}" in series.render()
assert from_dict(series, {"settings": [{"type": "Pad", "value": "2mm"}]}).settings[0].value == Length("2mm")
```

## What a node is

`Command`, `Environment` and `Passthrough` are frozen pydantic models. Building one does not validate it (`violations()` does);
assigning to a field raises `pydantic.ValidationError`, and `str(node)` is `repr(node)`. `node.model_fields_set` is the fields
the caller passed, a default given explicitly included; `to_dict` writes exactly those. A field cannot be named like an
attribute every component has (`copy`, `json`, `render`, a `model_` name: `TM-M045`).

```python
assert Fact(text="a").model_fields_set == {"text"}
assert to_dict(Fact(text="a")) == {"type": "Fact", "text": "a"}
```

## The document

Bare nodes are a document with nothing but content. A `Document` is the whole of one: its nodes and everything else a `.tex`
carries. `pkg.document(doc)` and `pkg.plan(doc)` take it alone.

```python
doc = Document(card, options=["a4paper"], settings=[Gap(Length("3mm"))])
tex = pkg.document(doc)
assert r"\documentclass[a4paper]{article}" in tex
assert r"\setlength{\dkGap}{3mm}" in tex
```

| Field | Is |
|---|---|
| `content` (the positional arguments) | the nodes of the body |
| `options` | class options, `[A-Za-z0-9][A-Za-z0-9=.-]*` (`TM-C006`) |
| `settings` | `Value` instances, written after the package ([Values](values.md#settings-for-a-document)) |
| `preamble` | a `PreambleSlots`, below |

## Layout

Each level of environment indents its content by two spaces; the output is the same everywhere, so committed documents diff
the same. Only the lines texmodel writes are indented: the first line of a call, `\begin`, `\end` and comments. A
`Passthrough` and the later lines of a call are verbatim, because their text is the author's and may be a `verbatim` body.
An environment whose body TeX reads verbatim should hold `Passthrough` children only. TeX skips spaces at the start of a
line, so the typeset result is the same.

```python
assert Card(Name(text="Rex"), Fact(text="a")).render().splitlines()[1] == r"  \dkName{Rex}"
```

## The preamble

`Document(..., preamble=PreambleSlots(before_class=, before_package=, after_package=))` places TeX where the document
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
tex = pkg.document(Document(card, preamble=slots))
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
`"type"`, an environment's children are its `content`, and a `Raw` field takes a string. `from_dict(Card, data)` is a node.

```python
data = {"content": [{"type": "Name", "text": "Fox"}, {"type": "Fact", "text": "Quick."}]}
loaded = from_dict(Card, data)
assert loaded.violations() == []                 # the grammar (counts, order) is checked here, as for any tree
assert to_dict(loaded) == {"type": "Card", "content": [{"type": "Name", "text": "Fox"}, {"type": "Fact", "text": "Quick."}]}
assert "$defs" in json_schema(Card)
```

Everything wrong comes at once as an `ExceptionGroup` of `ValidationError` (`TM-C020`), each with a path such as
`Card/Fact[2].text`.

`from_dict(pkg, data)` is a `Document`: the package says which components and values the names in the data are.
`content` is a list of nodes, `options` a list of strings, `settings` a list of `{"type": "Gap", "value": "3mm"}` and
`preamble` a mapping of slot to a list of TeX strings and typed entries (`{"type": "PdfInfo", "entries": {"Title": "Rex"}}`).
`to_dict(doc)` writes the same shape, leaving out what is empty. An entry in the wrong slot is `TM-C008` when the document
is rendered.

```python
saved = to_dict(Document(card, settings=[Gap(Length("3mm"))], preamble=slots))
assert saved["settings"] == [{"type": "Gap", "value": "3mm"}]
assert saved["preamble"]["before_class"] == [{"type": "RequireMetadata", "entries": {"lang": "en-GB"}}]
again = from_dict(pkg, saved)
assert pkg.document(again) == pkg.document(Document(card, settings=[Gap(Length("3mm"))], preamble=slots))
```

A renamed field keeps loading under its old key. `text: Text = field(renamed_from="body")` loads `{"body": "..."}`, writes
`"text"`, and the schema records `x-renamed-from`:

```python
assert from_dict(Name, {"body": "Fox"}).text == "Fox"
```

`field(doc=, meta=)` and a class-level `meta = {"audience": "deck"}` put a description and `x-` keys in the schema.

## A schema for the data

`texmodel schema` writes `json_schema(pkg)` to `[tool.texmodel] schema_output`: one JSON Schema for a `Document` (its root),
with a `$defs` entry for every command and environment (a child is told apart by its `"type"` constant), `Value.<Name>` for
every value and `<Name>Setting` for the data of one setting. Use it
for editor support and validators of the TOML or JSON that `from_dict` reads. It describes one package's data, so it needs a
single `package` in the configuration.

## Stored data that changed

`texmodel.history` reads stored data against today's model, for whoever migrates it (texpkg runs the migrations).
`problems` is everything that stops the data from loading, each a `Problem` with a data path, the reason, the stored
value and the schema of the field there; `unplaced` is a stored field the model no longer has, which loading would drop
without a word. `schema_changes` compares two schemas of one model and gives each change a `Level`: an optional field
added is `COMPATIBLE`, a field removed or a bound tightened is `BREAKING`, a field renamed with `renamed_from` keeps old
data loading.

```python
import copy

from texmodel.history import Level, problems, schema_changes, unplaced, worst

schema = json_schema(Card)
stored = {"type": "Card", "content": [{"type": "Name", "text": "Fox", "colour": "red"}, {"type": "Fact"}]}
assert [p.path for p in problems(Card, stored, schema)] == ["/content/1/text"]
assert [p.path for p in unplaced(stored, schema)] == ["/content/0/colour"]

shorter = copy.deepcopy(schema)
shorter["$defs"]["Fact"]["properties"]["text"]["maxLength"] = 80
assert worst(schema_changes(schema, shorter)) is Level.BREAKING
```

## Where a line came from

`pkg.plan(...)` takes the arguments of `pkg.document(...)` and returns a `Plan`: every output line with the path of what
wrote it (`Card[1]/Fact[0]`, `settings[0]`, `preamble.after_package[0]`).

```python
plan = pkg.plan(Document(card, preamble=slots))
assert plan.text.startswith("% deck document")
assert plan.lines[0].path == "header"
```

- `plan.text` is the document. Store `plan.to_json()` beside the committed file.
- `Plan.from_json(saved).edits(text)` names each hand edit by the path it had when it was written, even if the model has
  changed since. `plan.edits(text, ignore_comments=True)` skips lines that are comments on both sides.
- A changed line says which argument: `edit.fields` is `(FieldEdit("text", "Friendly"),)` when the change is inside one
  argument's text, empty when it is over the command name, a delimiter or several arguments. A baseline saved without
  `Line.spans` gives no fields. `texmodel.run.hand_edits.read_edits` reads the same edits with TeX, with typed values:
  [Testing](testing.md#hand-edits-read-by-tex).
- `edit.line` is where the edit is in the file, 1-based (`None` for a removed line), and `edit.file` the file, when
  given: `plan.edits(text, file=path)`. `edit.plan_line` is the plan's line it is about (for an added line, the one it
  follows).
- `edit.data_path` is where the edited node is in the document's `to_dict` data: `Card[0]/Fact[1]` is
  `PurePosixPath("/content/0/content/1")`, `settings[0]` is `/settings/0`; `None` for the header and the class line.
- `plan.path_of(39)` names the component behind a log's `input line 39`.
- `await Compiler().compile(src, out, plan=plan)` does that for every diagnostic in the source: `diagnostic.path` is the component
  behind its line. `plans={"deck.sty": pkg.render_plan()}` does the same for diagnostics in other files, by file name.

## Restoring hand edits

`restore(pkg, document, edits)` gives back the data that writes a hand-edited file: `document` is the one texmodel last
wrote, exactly as `pkg.plan(document)` rendered it (everything merged in that the file shows, a profile already
expanded), and `edits` are that plan's edits of the file (or `read_edits`'). An edit that does not match a line of that
plan is refused (`TM-X034`). A changed argument restores as its field's new
value; a node whose every line is deleted, or commented out as itself (`%`, then the line), is removed from its parent:
a command, an environment or a `Passthrough`; a `Comment` never is.
Regenerating writes no line in its place.

```python
from texmodel.restore import Reason, restore

written = Document(Card(Name(text="Rex"), Fact(text="Friendly."), Fact(text="Loud.")))
text = pkg.plan(written).text.replace(r"\dkFact{Friendly.}", r"\dkFact{Friendly \& calm.}")
text = text.replace(r"  \dkFact{Loud.}", r"%  \dkFact{Loud.}").replace(r"\dkName{Rex}", r"\dkName{R&D}")
restored = restore(pkg, written, pkg.plan(written).edits(text))
assert to_dict(restored.document)["content"][0]["content"][1:] == [{"type": "Fact", "text": "Friendly & calm."}]
(refused,) = restored.unapplied
assert refused.reason is Reason.INVALID_VALUE and refused.violation.code == "TM-C021"  # `&` unescaped
```

Every edit comes back once: in `applied`, or in `unapplied` with a `Reason` (a stable `TM-R` code). An edit is applied
only when the document with it writes the edited line exactly. One that writes another line is `MISMATCH`, with the line
it writes in `writes`. A removal the grammar refuses is `GRAMMAR`, with the grammar's violation. Lines that are not
data come back as `NO_DATA_CHANGE`, `NOT_DATA`, `SETTING` or `COMMENT` (a card's id is never restored), and an added
line as `ADDED_LINE`, with the node it stands in (`parent`, `""` for the document) and the child it follows (`after`,
`None` when first): the system that keeps the data decides what to do with them. Edits found against another
document are refused (`TM-X034`).
