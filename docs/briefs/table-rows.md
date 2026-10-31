# Draft: tables whose rows are typed nodes (`TableRow`)

Follows `docs/briefs/tables.md`. A consumer sets a block of rows (an icon, a label, a bold value) as typed row nodes in
a table and needs the schema, `Plan.edits`, `restore()` and `hand_edits()` to find one cell of one row. Today
`Table.node()` writes the rows as one `Passthrough`. Status: **built** (`std/tabularray.py`, `ext/table.py`, `run/hand_edits.py`; guide `docs/guide/tables.md`). Two things changed in the building: `read_edits` stubs `tblr`, `longtblr` and `talltblr` only (a stub cannot redefine the `booktabs` library's tables when the library is not loaded), and a body is derived when a row has none.

## The finding

A row cannot be an ordinary macro in `tblr`: tabularray splits its body at `&` and `\\` before it expands anything, so
`\newcommand{\apRow}[3]{#1 & #2 & #3 \\}` used in a body fails with "Misplaced alignment tab". tabularray's own answer is
the outer key `expand`: `\begin{tblr}[expand=\apRow]{...}` expands the macro once, then splits. Spiked and compiled
(LuaLaTeX, TeX Live 2025, the reference image):

| Question | Result |
|---|---|
| Typesetting | Same as literal rows in `tblr`, `talltblr`, `longtblr`; `rowhead`, header repeat, page breaks, captions, `row{n}`, `cell{}{}`, `hline{n}` all count macro rows as literal rows. |
| Cell content | Braces, `\%`, `\&`, minipages, boxes and a nested `tblr` in a cell need nothing special. |
| Several row macros | `expand=\a\b`, `expand={\a,\b}` or `expand+=` work; the bare `\a,\b` does not. |
| Row macro that calls another | Expansion is once: list both (`expand=\outer\inner`). |
| Row macros that do not work | `\NewDocumentCommand` (protected), `\NewExpandableDocumentCommand`, an optional first argument (`[1][]`, `\@ifnextchar`): "Misplaced alignment tab", input stack overflow or a mangled table. `\multicolumn` is refused by tabularray: use `\SetCell[c=2]{l}`. |
| Derived environment | `\NewTblrEnviron{prof}` with `\SetTblrOuter[prof]{expand=\apRow}` works (`\begin{prof}{}` needs an explicit inner argument). Not needed. |
| `hand_edits` (rows stubbed to log) | The table processes its body **four times**, so a stubbed row logs each call four times: `TM-X032`. Stubbing the table environment too (`Tblr`) gives exactly one log per call. |

Alternatives evaluated and dropped:

- **A literal `Row` node** that writes `a & b & c \\` itself: needs a new node kind in the core, and `hand_edits()` cannot stub
  it (it stubs control sequences). The macro-row route gives the same tree plus TeX-level reading.
- **Rewriting or absorbing tabularray, or plain `tabular`:** nothing to gain once `expand` works.
- **LuaLaTeX** (a collect-and-emit environment, counting calls inside the stub, callbacks): the collect-and-emit version typesets
  the same and logs once without stubbing the environment, but needs a Lua file, `tex.runtoks`, and loses `%` comments and `#`
  in arguments; no reliable signal de-duplicates the four passes; callbacks cannot attribute cells to source rows. Not worth it.

## The design

1. **`std.tabularray.TableRow`**, an abstract `Command` base (`abstract=True`), and `Anywhere(TableRow)` in `TABLE_BODY`. A
   package's row is `class ProfileRow(TableRow)` with `body = r"#icon & #label & #value \\"`, registered as any command
   (`\newcommand{\apProfileRow}[3]{...}`).
2. **Grammar and schema:** a child that is an instance of an abstract `Anywhere` kind floats like the kind itself;
   `Children` and `spec._reachable` enumerate the registered concrete subclasses (`_concrete_kinds`).
3. **`expand` is computed and checked.** A helper `expand_of(rows)` is the sorted-by-first-use list of the row commands of a
   table; `Table` sets `TblrOuter(expand=...)` with it. A `Tblr` with a `TableRow` child whose command is not in
   `outer.expand` is a `Violation` (new `TM-C` code): today it compiles to 32 TeX errors. A `TableRow` row macro that calls
   another row macro lists both.
4. **Declaration checks (`TM-M`):** a `TableRow` has an inline `body`, only mandatory arguments (an optional value is a mandatory
   argument that is empty when unset), and no `begin`/`end`.
5. **`Table(RowClass, rows, ...)`**: the model is a `TableRow` subclass whose fields carry `Col(...)` (width, alignment, style,
   `cells=`). `node()` returns a `Tblr` whose children are the row instances (a header, when `header=True`, is one `Passthrough`
   first). Refused with a `TM-M` code in this mode: `totals`, `subtotal`, `group_by`, `spans` and a `Format` that matters (the
   row's own body writes the cells); `highlights`, `look`, `caption`, `notes`, `long` and the column keys work. Mixed row kinds in
   one table are built by hand (`Tblr(*rows, outer=TblrOuter(expand=expand_of(rows)), ...)`); `Table` takes one class.
6. **`read_edits`** stubs the table environment whenever a stubbed class is a `TableRow` (every environment whose grammar holds
   `Anywhere(TableRow)`), and takes `stub=` for extra components. Without it a caller gets `TM-X032`.

## What works afterwards (spiked on a scratch copy)

| | Result |
|---|---|
| `violations()`, `to_dict`/`from_dict`, `json_schema(Tblr)` and `json_schema(pkg)` | Typed rows in the tree; two row classes in one table, a table inside the user's own environment: round trip equal, `$defs` for each row class. |
| `Plan.edits` and `restore()` | One cell: applied (`Tblr[0]/ProfileRow[0]`, field `label`). Two cells in two rows of different classes: both applied. A removed or commented-out row: applied. A bad value: `TM-R008`. A added row line: `TM-R005`; reordered rows: `TM-R006` (as for any container). |
| `read_edits(stub=[Tblr])` | The same edits, each changed field with its typed value. |
| The existing suite on the scratch copy | 1028 passed; one failure: the public API snapshot (`read_edits(stub=)`). |

## Changes to the repo

| # | File | Change | Size |
|---|---|---|---|
| 1 | `std/tabularray.py` | `TableRow`, `Anywhere(TableRow)`, `expand_of` | S |
| 2 | `components.py` | `_concrete_kinds`; the abstract-aware filter in `_grammar_violations`; `Children` | S |
| 3 | `spec.py` | `_reachable` uses `_concrete_kinds` | XS |
| 4 | `components.py` / `std/tabularray.py` | the `expand` check (`TM-C`), the `TableRow` declaration checks (`TM-M`) | S |
| 5 | `run/hand_edits.py` | stub the table environments of a `TableRow`; `stub=` | S |
| 6 | `ext/table.py` | `Table(RowClass, ...)` and its refusals; header optional | S-M |
| 7 | tests, guide (`tables.md`, `std.md`), `known-limitations.md`, plan, changelog, API snapshot | a `tex` compile test with two row classes and `expand`; hand edits through TeX | M |

## Risks

1. `_concrete_kinds` reads `__subclasses__()`: a row class not imported yet is missing from the schema, and rows of every package are
   in it. Filter by the registry (`__tm_package__`) now; by the document's package later.
2. Stubbing depends on the table environment being in the stub set: auto-stub by grammar (6) removes the trap.
3. Reorder and add-row edits are not restorable (`TM-R006`, `TM-R005`): as for any container.
4. `expand` is a token list: a forgotten class fails only in TeX unless check 4 is built.
5. A consumer's existing row command must become a cell row: its body writes `&` between cells, with plain `\newcommand`.

## Open

- `TableRow` public (add `__all__` to `std.tabularray`) or not.
- A row body derived from the fields (`body` omitted: `#a & #b & #c \\`) so a row class is only its fields.
- Whether `Col(width=...)` tied to a `Recorded` (the consumer's point 6) comes with this or after.
