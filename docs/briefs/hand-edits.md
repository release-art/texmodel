# Draft: restore the data from an edited document

Roadmap item 1. Status: **decided** (2026-10-29); nothing is built. The decisions are at the end.

## The job

A managing system generates a document from its structured data and commits it. A person edits the `.tex` by hand and
commits that. The system pulls, sees the file changed, and must bring its data back in step. texmodel's part:

> From the edited text and the document texmodel last wrote, **restore the data that would have produced the edit**;
> where it cannot, **return enough for the system to update its own store**.

What the system does with the result (map it to its records, ask a person, call an LLM on it) is the system's. Nobody is
present when it runs, so nothing here asks: what cannot be restored comes back as data, with a reason.

The consumer's process (synthetic in tests, `tests/consumers/card_deck/`): an LLM writes structured cards, the system
renders the deck, the deck's editor checks it out, edits it in a TeX editor during proofing, commits and pushes; one
editor per deck. The system ingests on the next pull. Regenerating over an edit that was not ingested stops and names
the card (texpkg's `save()`, `HandEditError`: built). Most edits are card text (a fact reworded to fit, a name
corrected); some drop a slot or a question from an over-set card, often by commenting the line out; whole cards are
rarely removed. Layout is not edited. Each card carries its id in a `Comment` before it, and paths are read against the
saved document, so reordering on regeneration cannot misplace an edit.

## What is built

| Step | Where |
|---|---|
| Each changed line, by the path of the node that wrote it, and kind (`ADDED`, `REMOVED`, `CHANGED`, `UNREAD`) | `Plan.edits(text)` |
| The argument a change lies in, and its new text | `Edit.fields`, `FieldEdit` |
| The new text as a typed value of the field's type, or the `Violation` saying it is none (`TM-C021`) | `testing.read_call` (Python); `texmodel.run.hand_edits.read_edits` (through TeX, with stubs) |
| Refusing to overwrite an edit that was not ingested | texpkg `Document.save()` |
| A plan path as a data path (`/content/1/content/0`) | texpkg `_internal/handedits.data_path` |

## Design

### One pure function

```py
from texmodel.restore import restore

restored = restore(pkg, document, edits)     # edits from Plan.edits(text), or from read_edits
restored.document     # the Document, with every edit that could be restored
restored.applied      # the edits it holds
restored.unapplied    # Unapplied(edit, reason, violation) for each one it does not: its Reason, and why
```

- `document` is the one texmodel last wrote (the system keeps it, as texpkg's saved tree, or rebuilds it from its data);
  `edits` are `Plan.edits` against that document's plan, or `read_edits`' (the same, read by TeX). No process is
  started: a typed value comes from the argument's text by the field's type, as `read_call` reads it.
- Every edit comes back, in `applied` or `unapplied`: none is dropped without a word.

### What restores

| Edit | Restored as |
|---|---|
| `CHANGED`, the change inside one or more arguments, each reading to a value of its field | the node with those fields replaced |
| `REMOVED`, every line of one node (a command's call; an environment's `\begin` to `\end`) | the node removed from its parent, when the grammar still holds |
| A call line turned into a comment of itself (`% \bbLeadFact{...}`) | the same as removing it; regeneration writes no line (decision 2) |

### What comes back unapplied, and why

Every unapplied edit carries one `Reason`, a member of one `@enum.unique` `StrEnum` whose values are new stable codes
(`TM-R0xx`). The enum is the one registry of reasons: a duplicate code fails at import, and a test fails on a `TM-R`
code written anywhere else in `src`. Where a check below it said why (`TM-C021`, the grammar), its `Violation` comes
with the reason.

| Edit | `Reason` |
|---|---|
| `UNREAD`: the text differs but TeX reads the same calls (spacing, a comment) | `NO_DATA_CHANGE` |
| A line of no node: the preamble, the header | `NOT_DATA` |
| A setting's line | `SETTING` |
| A `Comment`'s line (a card's id) | `COMMENT` |
| `ADDED`: a line the document did not have | `ADDED_LINE` (decision 5) |
| A change over a command name, a delimiter, several lines of one call, or no argument | `NOT_IN_ARGUMENT` |
| Some lines of a node removed or commented out; a commented line also edited | `PARTIAL_REMOVAL` |
| An argument that reads to no value of its type (an unbalanced brace, an unknown command) | `INVALID_VALUE`, with `TM-C021` |
| A removal or a comment-out the grammar does not allow (the only lead fact) | `GRAMMAR`, with its violation |
| Restored data that writes another line (`R&D` for `R\&D`) | `MISMATCH`, with the line texmodel would write |

### The gate: the restored data must write the edited line

An edit is applied only if `pkg.plan(restored.document)` writes exactly the edited line again (for a removal: no line).
That is the definition of "the data that would have produced it", checked rather than assumed. An edit that restores to
data writing something else (the person typed `R&D` where the text must be `R\&D`) is unapplied, with the line texmodel
would write, so the system can say what to fix. Tested as a law (hypothesis): for every applied edit, rendering the
restored document reproduces the edited file at that node.

### Paths for the system

`Plan` paths name nodes by class and position (`Card[1]/CardBack[1]/LabelledSlot[3]`). The system stores data, so each
edit also carries its data path into the document's `to_dict`, a `PurePosixPath` (`/content/1/content/0/content/3`), which is texpkg's
`data_path`, moved into texmodel as one model's history (plan §13 X11, texpkg V9). With the card's id `Comment` beside it
in the same parent, the system finds its record without counting.

## Tests

- Unit, on the synthetic card deck: a reworded fact, a corrected name, a dropped slot (deleted and commented out), a
  removed card, each restored and rendered back to the edited text; each unapplied kind with its code.
- The round-trip law above, over generated decks and generated edits.
- With TeX (`tex`): the same edits through `read_edits` restore the same document.

## Decisions needed

1. **The name and place** (decided 2026-10-29). `texmodel.restore.restore(pkg, document, edits) -> Restored`, a
   public module of the core, pure; a module function, not a `Package` method. Edits of another document's plan are
   refused (a `DeclarationError`), not returned.
2. **A removal restores, and a commented-out call is one** (decided 2026-10-29). A deleted or commented-out slot or
   question restores as removed from its card when the card's grammar still holds; when it does not, it comes back
   unapplied with the grammar's violation. The consumer stores the removal on the card, so regeneration does not bring it
   back. Regeneration writes nothing in its place, no comment and no marker: the removed line is in git. A comment-out
   counts when the line, leading spaces aside, is `%`, optional spaces and the original line unchanged; every line of an
   environment commented out removes it. Anything else (a commented line also edited, `%%`, part of an environment)
   comes back unapplied.
3. **The gate** (decided 2026-10-29). An edit is applied only when re-rendering writes the edited line exactly (for a
   removal: no line); otherwise it comes back unapplied with the line texmodel would write. Each edit is checked at its
   own line, so one failing edit does not hold back another on the same card.
4. **Non-data edits are returned, not dropped** (decided 2026-10-29). `UNREAD`, preamble, header, setting and
   id-comment edits come back unapplied, each kind with its own stable code, so the system can tell "nothing to ingest"
   from "nothing seen", and decides itself what `save()` overwrites. A card's id is never restored. Settings are not
   restored in the first version (layout is not edited); one more row in "What restores" when a consumer needs it.
5. **Added lines** (decided 2026-10-29). Unapplied in the first version, `Reason.ADDED_LINE`, with the line's text and
   where it was added (the parent's plan and data path, the line it follows); the system acts on it. The next step, once the consumer
   needs it, is pure: a one-line call of a known command, its arguments read by `read_call`, inserted where the grammar
   allows and checked by the gate. An added environment or card stays unapplied.
6. **`data_path` moves from texpkg** (decided, 2026-10-29), with this item, so every edit carries both paths. A data path
   is a `pathlib.PurePosixPath` (`PurePosixPath("/content/3/content/1")`), not a string: its parts are the keys and
   indices of the document's `to_dict` data.

## Steps

0. `texmodel.run` first (`docs/briefs/run.md`), so `read_edits` is already at its new path.
1. `texmodel.restore` with changed arguments and the gate; the `Reason` enum and its registry test.
2. Removals and comment-outs, against the grammar.
3. `data_path` from texpkg; texpkg's `Document` then restores its saved tree with it.
4. The round-trip law and the `read_edits` compile test.
5. Guide (`documents.md`, `testing.md`), known limitations, the plan's decisions log, changelog.
