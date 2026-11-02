# Testing

A component's body decides what it passes on to other components. Two tiers test that: a fast one in Python and one that
compiles. Layout is not covered: this tests what a component passes on, not how it looks.

## Stubs, without TeX

`expand(node, stubs=[Fact])` (`texmodel.testing`) walks the bodies with the node's values and returns the body text and a
`Call` for every stubbed component, in order.

```python
from texmodel.body import Hole
from texmodel.components import Command, Environment
from texmodel.package import Package
from texmodel.testing import Call, expand
from texmodel.types import Text

pkg = Package("base-kit", prefix="bk")


@pkg.command
class Fact(Command):
    """A fact."""

    text: Text
    body = r"\par #text\par"


@pkg.command
class Entry(Command):
    """A fact with a rule above it."""

    text: Text

    def body(self):
        yield r"\par\hrule"
        yield Fact.call(Hole("text"))


@pkg.environment
class Section(Environment):
    """A titled section."""

    title: Text
    children = [Entry.times.any()]
    begin = r"\begin{center}#title"
    end = r"\end{center}"


section = Section(Entry(text="First"), Entry(text="R&D 50%"), title="Notes")
calls = [c for c in expand(section, stubs=[Fact]) if isinstance(c, Call)]
assert calls == [Call("bkFact", ("First",)), Call("bkFact", (r"R\&D 50\%",))]
```

## Stubs, in TeX

The compile tier checks that the real macros do the same. `pkg.test_document(section, stub=[Fact])` loads the real packages
and replaces each stub with a macro that writes `texmodel:probe:callN=bkFact{...}` to the log.
`await texmodel.run.testkit.run_probes(compiler, tex, files={"base-kit.sty": ...})` compiles it and returns the probes, which
`Call.parse` reads. Arguments are shown as `\detokenize` shows them (a space after each control word), so both tiers agree.

## Hand edits, read from the calls

`Plan.edits(text)` finds a hand edit by line. `texmodel.hand_edits.read_edits(plan, text, pkg)` reads the calls of the
packages' commands and environments in the plan's text and in the edited one, by each component's signature, and compares
them. No TeX runs, and the edited document need not compile.

```py
from texmodel.hand_edits import read_edits

edits = read_edits(plan, hand_edited_text, pkg)
for e in edits:
    e.path, e.kind                    # "Box[0]/Item[1]", CHANGED
    e.fields[0].arg, e.fields[0].value  # "count", 3: the typed value the argument now holds
    e.fields[0].violation             # TM-C021 when the text is not of the field's type
```

An edit that reads as the same calls (a comment, spacing, a group around the call) or whose call cannot be read (a missing
argument, a `}` first) is `UNREAD`; a call that does not run (`\iffalse`, `%`) is `REMOVED`. It reads what the document
writes: a call a macro of the document makes is found where the macro is defined, not where it is used. The tests hold the
reader to the calls real LuaTeX makes through stubs (`texmodel.testing.stub_tex`). What it cannot see is in
[known limitations](../known-limitations.md#hand-edits).

## Checking a library block

`await texmodel.run.testkit.check_library(compiler, pkg)` compiles a document that asks TeX whether each name a library block
should define is defined, and with how many arguments: see [TeX you already have](adopting.md#what-check-reports).

## Compile as data

`await Compiler().compile(src, out, plan=plan)` gives typed diagnostics. With a `Plan` each names the component behind its
line. See [Building and compiling](build.md).
