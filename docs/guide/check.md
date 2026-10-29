# Check committed files

Commit what texmodel writes, and let CI fail when it is out of date.

## Configuration

```toml
# pyproject.toml
[tool.texmodel]
package = "acme_cards:pkg"
output = "generated"
```

`package` is a pointer: `dotted.module:object`, `dotted.module:namespace.object` (attributes are followed), or
`dotted.module:getter()` (called with no arguments; its result is used).

```toml
package = "acme_cards.decks:Decks.birds"      # or "acme_cards.decks:make_package()"
```

A family of packages (a core, its bases, one per series; a series names its base with `Package(..., base=)`, see
[Documents](documents.md#a-package-built-on-another)) is a list of pointers, or one pointer to an iterable of `Package`s.
`build` and `check` cover them all together, and a package name must be unique because it is a file name.

```toml
package = ["acme_cards.core:pkg", "acme_cards.birds:pkg"]      # or "acme_cards.family:all_packages()"
```

## Commands

```zsh
texmodel build              # writes generated/acme-cards.sty
texmodel render docs:card   # writes card.tex from `card = pkg.document(...)` (or a function returning one); -o to choose
texmodel check              # exit 1 if a committed generated file is stale, missing or orphaned
texmodel schema             # writes the JSON Schema of the package's data to schema_output
```

A stale line names its component: `changed generated/acme-cards.sty Fact: ...`. The header records the generator version
(`generated with texmodel X.Y.Z`), so when a stale file was written by another version, `check` says what the upgrade
explains of it: only the version line, the releases in between that changed generated output and how, or none, and then
the difference is a hand edit or a change to your declarations:

```text
note     acme-cards.sty: generated with texmodel 0.9.0, current is 0.10.0; output changed in 0.10.0 (`ext.fit` declares
         its two public lengths with `\newlength`): run `texmodel build`
```

A minor release may change generated output; a patch release never does. Each one that does says so in the changelog
(`Output change: ...`), and `texmodel.drift.OUTPUT_CHANGES` carries the same list.

## Committed documents

A document is checked the same way, with a pointer to a `Plan` (or a `str`) that the model renders:

```toml
[tool.texmodel.documents]
"deck.tex" = "deck.build:plan()"
```

`texmodel check` renders each pointer from today's model and compares it with the committed file, like `terraform plan`.
For a `Plan` every difference names the component that writes the line
(`changed  deck.tex Card[1]/CardBack[1]/LabelledSlot[3]: ...`), so a hand edit and a stale render read the same. A `str` is
compared whole. Exit 1 on any difference. `texmodel render` with no pointer rewrites every configured document.

## In code

`texmodel.drift` is what `check` uses, `texmodel.pointer` resolves `module:object` pointers (a package, a document, a
`Plan`), and `texmodel.bundle` copies a manifest of files and refuses if any is missing (`stale` compares bytes, not
timestamps).
