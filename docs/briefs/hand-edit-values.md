# Hand edits by field, with the new value

Status: the API is built (no CLI yet). Relates to roadmap X2 and plan §21a item 5/6. Measurements behind it:
[hand-edit-probe-spec.md](hand-edit-probe-spec.md).

## What exists

`Plan` (`plan.py`) records one `Line(path, tex, spans)` per output line. `Plan.edits(text)` diffs a file against it by line and
names each edit by the path of the node that wrote the line (`Card[1]/CardBack[1]/Name[0]`). Two layers say more than the path:

1. **Without TeX**: `Edit.fields` names the argument a `CHANGED` line changed.
2. **With TeX**: `texmodel_build.hand_edits.read_edits` reads the calls TeX makes, so the value is typed, a bad value is a
   `Violation`, and what TeX reads the same is `UNREAD`.

## Without TeX: `Line.spans`, `Edit.fields`

`render.call_arguments` yields `(arg, start, end)` for each written slot's text (delimiters excluded; a token is its own text),
`components.call_line(node)` shifts them past the command name or `\begin{name}`, and `Package.plan` stores them as `Span`s on the
line. A call over several lines has none. `Plan.to_json` writes spans as a third element only for a line that has them;
`from_json` accepts the two-element form (no spans: node-level edits only).

For a `CHANGED` line, `_fields` aligns the expected and found text with `difflib.SequenceMatcher` at character level.

- every change inside one span's text: `fields = (FieldEdit(arg, found), ...)`, `found` the argument's text in the file;
- a change over a delimiter, the command name or text outside every argument (including an extra argument): `fields = ()`,
  the line text is still reported;
- a `fill` (written for an omitted optional before a later one) has no span;
- `ADDED` and `REMOVED` lines have no fields.

`FieldEdit(arg, found, value=None, violation=None)`, `Span(arg, start, end)` and `Edit.fields` are in `texmodel.plan`.

## With TeX: `read_edits`

```py
from texmodel_build.hand_edits import read_edits

edits = read_edits(compiler, plan, hand_edited_text, pkg, files={...})   # list[Edit]
```

1. Every command and environment of `packages` is stubbed (`stub_tex`) before `\begin{document}`; each package's generated
   `.sty` (`Package.files()`) and `files` are written beside the document. The plan's own text is compiled as the baseline,
   then the edited text (`run_probes`, `Call.parse`). A document that does not compile raises `CompileError`.
2. The plan lines that call a stubbed component (a line starting `\name`, `\begin{name}` or `\end{name}`) are 1:1 with the
   baseline's calls, each with its path; if not, `TM-X032`. No component to stub is `TM-X033`.
3. Calls are aligned with `difflib` over the **whole call** `(kind, name, args)`, `autojunk=False`, pairing by position inside a
   `replace` block (aligning by name alone names the wrong one of a repeated command). Another command on the line is a
   `CHANGED` without fields; the same command with other arguments is a `CHANGED` with one `FieldEdit` per differing argument.
4. Each argument is read by `texmodel.testing.read_call(cls, call)`: its field (through `tex_arguments`), its text and the value
   it reads back to, by the field's `BodyKind` (`_internal/read.py`, the inverse of `value_text` on the `\detokenize`d text:
   a space after each control word, runs of spaces one). Text that is not of the field's type has `value=None` and a
   `Violation` (`TM-C021`, path `Meter[1].count`); what the text cannot say has neither. An empty optional has no value.
   A field whose old and new text read to the same value (`.5` for `0.5`) is no edit.
5. Merge with `Plan.edits(text)`. A `CHANGED` line takes the fields of the probe's edit at its `(path, kind)`, or is
   `EditKind.UNREAD` (comment, spacing, `{...}` around the call, an extra argument, an unstubbed line). An `ADDED` or
   `REMOVED` line stays as the line diff has it and uses up one probe edit about the same call (kind and name), because equal
   neighbouring calls cannot be told apart and the two diffs may name different ones. What is left is what only TeX saw (a
   call lost to `\iffalse` or `%`); an inserted call belongs to the call before it, or to `document`.

What each kind reads back to, and what the probe cannot see (an extra argument, an unstubbed line, a body error, a redefined
stub, a missing argument swallowing the next call, omitted versus `[]`): the spec, and `docs/known-limitations.md`. The routes
are complementary: a line the line diff calls `CHANGED` while the calls are equal is never reported as clean.

`read_value` per `BodyKind`: text unescapes (a control sequence left over is a violation), `Raw` is the detokenized text, a
`Length` is a number and unit (spaces allowed) or a TeX expression, `int` and `float` are strict numbers, `bool` the written
pair, `Choice` the member by its TeX, a token `\BooleanTrue` or `\BooleanFalse`, a tuple or list split on `sep` (a record is a
plain tuple). A key list, a PDF string and a `Raw` subclass are not read.

## Not built

- A CLI: `texmodel check` stays TeX-free (`texmodel` never imports `texmodel_build`); the probe would be a command of
  `texmodel-build`. Printing `fields` in `check`'s hand-edit report is also open.
- `Doc.apply(edits)`, once the edits are trusted.
- Settings (`Value`s) read by TeX: `\the\lbGap`, `\iflbFlag`, `\extractcolorspec` (spec, "Settings"); each kind would supply its
  probe TeX. The line diff already names a setting.
- A tree-aware diff (a move across environments reads as the close moved) and a scan for a redefined stubbed macro.
- Key lists, PDF strings, bodies built from `Seq`/`Group`/`Hole` (an edit inside one is raw text; N1: no parser), keyed children,
  the ignore marker and the import hook (X2).
