# Spike: the probe route for hand edits, measured

Status: measured, and built as `texmodel_build.hand_edits.read_edits` (see [hand-edit-values.md](hand-edit-values.md)); the rules
below say where the build follows them.
Scripts are in the session scratchpad, not in the repo; they use only `stub_tex`, `run_probes`, `Call.parse` and `Plan`.

## What was run

A synthetic package (`lab`, prefix `lb`: text, optional `[..]`, `Star`, `PAREN` tuple, `Length`, `float`, `int`, `bool`,
`Choice`, `KeyVals`, a body that calls another component, two environments, a `Comment`, four `Value`s) plus the
`card_deck` consumer. Each case: render with `pkg.plan`, hand-edit the text, put `stub_tex(every component)` before
`\begin{document}`, compile in the reference image, read the `callN` probes, compare with the plan. About 60 cases.

## The method that works

1. **Expected calls** are the stubbed lines of the plan, in order, each with its path; an environment's first line opens,
   its last closes. (The spike took this from the path's last segment; the real code should take it from the node tree,
   as `expand` does.)
2. **Stub every component of every package the document loads.** Then calls and plan lines are 1:1. A real (unstubbed)
   component that calls a stubbed one produces calls with no plan line (`Twice` real, `Para` stubbed: one line, two calls).
3. **Align by the whole call** `(kind, name, args)` with `difflib.SequenceMatcher(autojunk=False)`. Aligning by name alone
   misattributes a deleted repeated command (card-deck slots); by whole call it does not. Inside a `replace` block, pair
   calls by position.
4. A compile error is a finding and nothing is read (`TM-X020` unbalanced environment, `TM-X010` undefined macro).
5. Merge with the line diff by path (below): the probe sees what TeX executes, the line diff sees every line.

Cost: 0.6 s per compile on average (1.6 s max) with the image warm; 5000 calls compile and diff in under a second.

## What a call gives, per argument kind

Arguments come in TeX order (the optional one first), `\detokenize`d: a space after each control word, runs of spaces one.

| Kind | Probe shows | `read_value` does |
| --- | --- | --- |
| `Text` | `A\&E`, `\textasciitilde {}b`, `two spaces` (3 spaces became 1) | undo the escapes, spaces and the `{}` after `\textasciitilde`; compare after collapsing spaces on both sides; other control sequences (`\today `) are TeX in a `Text` field: a violation |
| `Raw` | the TeX, detokenized (`\textbf {x}`) | compare with `detokenized(original)` |
| `Length` | as written: `3cm`, `3 cm`, `2\linewidth `, `\linewidth ` | parse number and unit, else an expression; `3mm` vs `0.3 cm` differ by 1 sp in TeX, so equality by value needs TeX or a tolerance |
| `float`, `int` | `0.12346` (five decimals), `.5`, `-1`, `three` | parse; `.5` equals `0.5`, so compare values, not text; `three` is a violation |
| `bool` | `true`, `false`, `maybe` | the written pair; anything else is a violation |
| `Choice` | `\lbLow ` | strip the space, find the member by its TeX; `\lbMid ` is a violation (nothing in TeX complains) |
| `Star` / token | `\BooleanTrue `, `\BooleanFalse ` | the two tokens |
| tuple | `1,-2` | split on the declared separator |
| `KeyVals` | `max width=3cm,center,extra={a,b=c]}` | needs its `KeyRules` to read; out of scope, value unknown |
| optional, left out | `''` | `''` is `None`: omitted and `[]` are the same call (`\lbNote[]{q}` equals `\lbNote{q}`) |

Every edited scalar compiled: the stubs never check a value. `read_call` (`texmodel.testing`, per `BodyKind`) is where a bad value is found: `TM-C021`.

## What an edit looks like

| Hand edit | Probe | Line diff (`Plan.edits`) |
| --- | --- | --- |
| field text, optional, star, env title changed | `replace`, old and new args, same path | `CHANGED` path only |
| command renamed (`Para` to `Note`) | `replace`, args differ in shape | `CHANGED` |
| command added or deleted | `insert` / `delete` with args | `ADDED` / `REMOVED` |
| two identical siblings, one deleted | the first is named | the second is named (rule needed, below) |
| environment begin and end both deleted | two `delete`s, same path | same |
| environment end alone deleted, or extra end | compile error, nothing read | reported |
| Note moved out of its environment | one `insert` and one `delete` of the environment's close, not "Note moved" | `REMOVED` Note, `ADDED` close |
| Inner nested in Inner | `insert` of both calls, nesting is in the open/close pairs | `ADDED` lines |
| trailing comment, space before `{`, wrapping in `{...}` | no change (right: same call) | `CHANGED` |
| argument split over lines, blank line inside | `z z`, `z \par z` | `CHANGED` + `ADDED` lines |
| `\iffalse` around a call, or `%` in front | `delete` (what TeX runs) | `CHANGED` / `ADDED`, wrongly pathed |
| unstubbed line added (`\vspace`) | no change | `ADDED` |
| extra argument `\lbPara{z}{extra}` | **no change**: the stray group is typeset, not seen | `CHANGED` |
| missing argument `\lbPara` | swallows the next token: `\lbPara ` as the argument and the next call gone (one edit, two findings) | `CHANGED` |
| `\def\x{\lbPara{m}}\x\x` in one line | two calls, one has no path | `CHANGED` |
| `\renewcommand{\lbPara}...` before `\begin{document}` | no change: the stub wins, the user's redefinition is lost | `ADDED` |
| same, after `\begin{document}` | every `Para` call vanishes: a mass `delete` | `ADDED` |
| `\verb|z|` in an argument | read as `\verb |z|`, no error (the real macro would error) | `CHANGED` |

## Rules the spec needs

1. **Classify** each aligned pair: *unchanged*; *field changed* (same kind and name, per-argument text differs); *replaced*;
   *deleted*; *inserted*. Argument index maps to a field name through `tex_arguments`.
2. **Unread change**: the line diff says `CHANGED` but the calls are equal. Cause is a comment, spacing, a group, an extra
   argument or an unstubbed addition; the probe cannot tell harmless from harmful, so report it as such, never as clean.
3. **Tie-break** for equal neighbouring calls: one rule for probe and line diff (the two disagree today). The paths of
   a deleted or inserted run of equal calls are interchangeable. Built: an added or removed line edit uses up one probe edit
   about the same call (kind and name), whichever path each names.
4. **A stubbed macro redefined in the text** (`\renewcommand`, `\let`, `\def` of a component's control sequence): scan the
   edited text for it (regex level, as the scan is today) and report it; do not report the vanished calls as deletions.
5. **Compile success of the probe is not compile success of the document.** Stubs never run the real bodies, so a value
   that breaks a body (`\verb`, a bad length) passes. `read_edits` documents it.
6. **Tree-aware diff** is possible only here: the open and close calls give nesting, the line diff has none. A move across
   environments can be reported as a move later; the flat diff reports the close as moved.

## Settings (`Value`s)

A setting is one plan line, so the line diff names it. TeX can also read it, with TeX the `ValueKind` supplies (a second
hook, `ValueKind.probe`; not built):

| Kind | Probe TeX | Result |
| --- | --- | --- |
| `Length` | `\the\lbGap` | `8.53581pt` for `3mm`, `8.5359pt` for `0.3 cm`, `690.0pt` for `2\linewidth`: normalised, in context |
| `bool` | `\iflbCompact yes\else no\fi` | `yes` / `no` |
| `Text`, `Raw` | `\detokenize\expandafter{\lbDeckName}` | `R\&D`, `R\&D \today ` |
| `Colour` | `\extractcolorspec{lb-ink}\cs` then `\detokenize\expandafter{\cs}` | `{cmyk}{0,0,0,0.5}` for `0.5`, `0.50`, `.5`; `1/2` reads as `1`: TeX's reading, not ours |

(Reading a colour through `\color@name` gives the macro's name, not its value; `\extractcolorspec` is the public way.)
Settings are optional for a first version: the line diff already attributes them.

## What was built from it

- Alignment is over the whole call, with the merge above. `Edit.fields` from the span diff and from the probe are one type,
  `FieldEdit(arg, found, value, violation)`.
- Reading is per `BodyKind` (`_internal/read.py`; `ValueKind` is for settings and was not needed). The law is
  `read(detokenized(written)) == value`; a violation is `TM-C021`, a baseline whose lines and calls disagree `TM-X032`, no
  component to stub `TM-X033`. A field whose old and new text read to the same value is no edit.
- Not built: the redefinition scan (rule 4), a tree-aware diff (rule 6), settings probes, a CLI.

## Not measured

Hand-written `Seq`/`Group` bodies of a component that is not stubbed (no calls to read), keyed children (X2), environments
declared with `\NewDocumentEnvironment` beyond `Inner`/`Outer`, adopted packages, a cold image (AGENTS: minutes), documents
with `\include`d files (the stub is injected into one file), and a `Doc.apply(edits)`.
