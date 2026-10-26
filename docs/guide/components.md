# Components

A component is a Python class that becomes a TeX definition: a `Command` is a `\newcommand`, an `Environment` is a
`\newenvironment`. Register it with a package and `pkg.render()` writes it. The blocks on this page run in order, as one
module.

```python
from texmodel.body import Cs, Group, Hole, Lit, Seq, TexRaw, Whitespace
from texmodel.components import Anywhere, Command, Environment, Passthrough
from texmodel.package import Package
from texmodel.types import Choice, Raw, Text

pkg = Package("kit", prefix="bk")
```

## Commands

The fields are the arguments. The docstring is required. `#name` in the body is the argument called `name`; a `#name` that is
not a field, or an argument the body never uses, is refused when the class is defined.

```python
@pkg.command
class Fact(Command):
    """One short sentence."""

    text: Text
    body = r"\par\noindent #text\par"
```

## Where a body comes from

A body is TeX you point at, never found by name:

- a string (dedented, so a triple-quoted string reads as it renders);
- a `TemplateRef("fact.tex")`, a file next to the defining module (the file is read when the class is defined, through `importlib.resources`, so a module imported from a zip works);
- a `body` method returning either, or a sequence or generator of pieces.

```py
body = TemplateRef("fact.tex")
```

Each piece can be a `TexRaw` with its own `Whitespace` policy. `TRIM` writes the `%` at line ends for you; `KEEP` (the
default, set per package with `Package(whitespace=)`) writes lines as given.

```python
@pkg.command
class Quote(Command):
    """A quotation."""

    text: Text

    def body(self):
        yield TexRaw(
            r"""
            \par\noindent
            {\itshape #text}
            """,
            whitespace=Whitespace.TRIM,
        )
        yield r"\par"
```

## Environments

An environment has `begin` and `end` in the same way, and `children`, the grammar of what it may contain.

```python
@pkg.environment
class Panel(Environment):
    """A titled panel."""

    title: Text
    children = [Fact.times(1, 3), Quote.times.any()]
    begin = r"\begin{minipage}{\linewidth}\textbf{#title}"
    end = r"\end{minipage}"
```

`X.times(2, 3)` is two to three, `X.times.any()` zero or more, `X.times.at_least_one()` one or more. Terms are in order, so a `Passthrough` listed last goes after the facts.
`Anywhere(Heading)` allows a component anywhere among the other children and does not count against the ordered terms
(`TM-M029` if it is also an ordered term). `Passthrough(Raw(...))` writes its TeX as it is and is accepted only where a
grammar lists it:

```python
@pkg.command
class Heading(Command):
    """A heading."""

    text: Text
    body = r"\par\textbf{#text}\par"


@pkg.environment
class Page(Environment):
    """A page."""

    children = [Anywhere(Heading), Fact.times(2, 3), Passthrough.times.any()]
    begin = r"\begin{minipage}{\linewidth}"
    end = r"\end{minipage}"


page = Page(Heading("Facts"), Fact("a"), Fact("b"), Passthrough(Raw(r"\vspace{1mm}")))
assert page.validate() == []
```

## Calling another component

A body calls another component by Python binding. The call is checked against the target's arguments and written with the
target's prefix. A target in another package makes that package a `\RequirePackage` of the generated `.sty`. A target
must be registered before the body that calls it.

```python
@pkg.command
class Entry(Command):
    """A fact with a rule above it."""

    text: Text

    def body(self):
        yield r"\par\hrule"
        yield Fact.call(Hole("text"))        # \bkFact{#1}


@pkg.environment
class Section(Environment):
    """A titled panel."""

    title: Text
    begin = Panel.open(title=Hole("title"))   # \begin{bkPanel}{#1}
    end = Panel.close()                       # \end{bkPanel}
```

`Fact.call(...)` takes the required arguments positionally and the optional one by keyword
(`Slot.call(Hole("t"), label="x")`). An environment's arguments are all keywords.

## Shared bases

Components that repeat a body or a grammar share a base declared `abstract=True`. It carries fields, `body` (or `begin`
and `end`) and `children`; it needs no docstring and may have any Python name; it is never registered (`TM-M043`); its
subclasses inherit all of it.

```python
class _Image(Command, abstract=True):
    src: Text

    def body(self):
        return r"\includegraphics{#src}"


@pkg.command
class Photo(_Image):
    """A photo."""
```

## Bodies built from pieces

A body can be built from pieces that are well-formed by construction, so a generator cannot write an unbalanced brace or
a bad control word.

| Piece | Writes |
|---|---|
| `Group(...)` | `{...}` |
| `Seq(...)` | the same, without braces |
| `Cs("par")` | a control word: letters and `@` only (`TM-M027`) |
| `Lit("50% & co")` | text, escaped as a `Text` field is |
| `Hole`, `Ref`, `Raw` | go inside |

A space follows a control word when the next text could continue its name. Loops and conditions are plain Python:

```python
import enum


@enum.unique
class Level(Choice):
    LOW = Raw(r"\lvLow")
    HIGH = Raw(r"\lvHigh")


@pkg.command
class Rating(Command):
    """Says which level it has."""

    level: Level

    def body(self):
        for member in Level:     # one branch per member, chosen when TeX expands the call
            yield Seq(Cs("ifx"), Hole("level"), member.value, Group(Lit(member.name)), Cs("fi"))
```

```latex
\ifx #1\lvLow{LOW}\fi
\ifx #1\lvHigh{HIGH}\fi
```

A `Choice` is an enum whose members carry their TeX: a `Raw` passes through, a `str` is escaped. Data names a member by
its name. texmodel writes this TeX and never reads TeX it did not write.

## Comments

A `Comment` writes every line prefixed `% `, so a value cannot leave it. It is a body piece (`yield Comment("why this is
3mm")`) and a document node, transparent to the grammar: not counted, never listed.

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


text = pkg.document(CardHeader("Red Fox", "11111111-aaaa"), Fact("x"))
assert "% Card: Red Fox" in text and "%   id: 11111111-aaaa" in text
```

`from_dict(cls, data, comments=[CardHeader])` and `json_schema(cls, comments=[...])` know it as a child
([Documents](documents.md)).

## expl3

expl3 is a syntax mode, not a typed language: texmodel has no vocabulary of `\fp_` or `\seq_` functions, and the compile
tells you when one is wrong. Give each `TexRaw`, `TemplateRef` and `Cs` that is expl3 `syntax=Syntax.EXPL3`. A body is in
one syntax (`TM-M031`). The definition is then wrapped in `\ExplSyntaxOn` / `\ExplSyntaxOff`, no `%` is added at line ends,
and `Lit` writes `~` for a space. A component whose `cs` has `_` or `:` says `syntax = Syntax.EXPL3`. To carry whole
blocks of expl3 into the `.sty`, see [libraries](adopting.md#library-blocks).
