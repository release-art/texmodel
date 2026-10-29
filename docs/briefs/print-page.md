# Draft: package options, and a print page chosen at load time

Roadmap item 2. Status: **built** (steps 1 to 3 and the compile tests); step 4 waits for the consumer's files. Decided: the options section sits right after the `\RequirePackage`
lines (1), one `nocrop` flag for the sheet, the boxes and the marks (2), margins that turn with a landscape
sheet (3), the API is a `Package.option` method (4), a document's option settings go into `\usepackage[...]` (5), and
options are flags, lengths and choices only (6).

## What the consumer needs

`PrintPage` (0.9.0) writes one sheet, fixed when the package is generated. The consumer decides at TeX run time, from
package options:

1. **The sheet.** `nocrop` is the preview: the trim alone. Without it, the print build: trim, bleed and crop margin.
2. **Landscape.** `landscape` swaps the trim's width and height.
3. **Crop marks.** The print build passes geometry's `showcrop`, and other parts of the package read its flag
   (`\ifbbshowcrop`).
4. **Page boxes** that follow the sheet chosen.

Settled (their reply of 2026-10-29): margins are measured from the trim, the type area is the same on both sheets
(91 × 135 mm on their card), and they give up the hand calibration of the preview's top margin.

## Part 1: package options (core)

LaTeX processes a package's options once, so options are the package's, and every module that needs one registers it.
Today `ColourSpace` writes its own `\ProcessOptions`, and a second module that did the same would break it.

### Registration

```py
crop = pkg.option("crop", flag=True, inverse="nocrop", doc="The print build: bleed, crop margin, crop marks.",
                  cs="bbshowcrop")
bleed = pkg.option("bleed", length=Length("3mm"), doc="The bleed past the trim.")
accent = pkg.option("accent", choice=Accent.SLATE, doc="The accent of the deck.")
```

- `Package.option` registers one option and returns the `Value` that holds it, so the package's bodies and documents use
  it like any value.
- A module registers its options when it is added to a package (`ColourSpace().declare(pkg)`, `page.declare(pkg)`).
- **The same name twice is fine when the declaration is the same**: the second call returns the option the first made,
  so two modules share one option (a `landscape` read by the page and by a layout module). **A different declaration is
  an error** (`TM-M073`): another default, another kind, or another inverse name. This is `make_value`'s rule (`TM-M007`).

### One way to write them

- Every option is a key of the l3keys family named after the package, all of them processed once by
  `\ProcessKeyOptions` (the LaTeX kernel's key-value options; the reference image has LaTeX 2025-11). `\DeclareOption`
  and `\ProcessOptions` are not used.
- Every key is `.usage:n = load`: it is set when the package loads, and TeX refuses it after (measured).
- The register an option sets is a LaTeX2e one, declared with its default in the options section: `\newif` for a flag,
  `\newlength` for a length, `\newcommand` for a choice. Hand-written TeX reads it as usual (`\ifbbshowcrop`,
  `\the\bbBleed`), and the scanner reads its declaration (`declared()`).
- A key's name is the name given: a LaTeX option name, lowercase letters, digits and `-` (`TM-M072` otherwise).

| Option | In a document | Key |
|---|---|---|
| flag | `crop`, `crop=false`; its `inverse` `nocrop` | `.legacy_if_set:n` / `.legacy_if_set_inverse:n`, `.default:n = true` |
| length | `bleed=2mm` | `.code:n = \setlength{\bbBleed}{#1}`, `.value_required:n` |
| choice | `accent=moss` | one `.code:n` per `Choice` member (`accent / moss`), setting `\bbAccent` to the member's TeX |

The options section of the `.sty`:

```tex
\newif\ifbbshowcrop
\bbshowcroptrue
\newlength{\bbBleed}
\setlength{\bbBleed}{3mm}
\newcommand{\bbAccent}{slate}
\ExplSyntaxOn
\keys_define:nn { brainy-boo }
  {
    crop .legacy_if_set:n = bbshowcrop , crop .default:n = true , crop .usage:n = load ,
    nocrop .legacy_if_set_inverse:n = bbshowcrop , nocrop .default:n = true , nocrop .usage:n = load ,
    bleed .code:n = \setlength { \bbBleed } {#1} , bleed .value_required:n = true , bleed .usage:n = load ,
    accent .choice: , accent .usage:n = load ,
    accent / slate .code:n = \renewcommand { \bbAccent } { slate } ,
    accent / moss .code:n = \renewcommand { \bbAccent } { moss } ,
  }
\ProcessKeyOptions [ brainy-boo ]
\ExplSyntaxOff
```

Measured in the reference image with a synthetic package: the defaults hold with no option; `\documentclass[nocrop]`
reaches the package; `\usepackage[bleed=2mm, accent=moss]` sets both; `accent=pink` is a TeX error; setting `bleed`
after the package has loaded is a TeX error.

### Only three kinds

A flag, a `Length` and a `Choice`: what selects a build. A text, a colour or a key list is a setting, written after
`\usepackage` as today: an option value travels through the class's option list, where a comma or a brace in it is
mangled. (Open: 6.)

### Documents

A document sets an option the way it sets any value, and texmodel writes it where it takes effect:

```py
Document(card, settings=[crop(False), bleed(Length("2mm"))])
# \usepackage[crop=false, bleed=2mm]{brainy-boo}   (not after it, where it would be too late)
```

The value is checked by its type, as a setting is (a `Choice` member, a `Length`), and written by texmodel. Other values
are still set after `\usepackage`. `Document(options=["nocrop"])` stays a class option and works too, as LaTeX passes
global options to the packages that declare them, but it is not checked. (Open: 5.)

### `ColourSpace`

It registers one flag, `cmyk` with the inverse `rgb`, default `Build.CMYK`. Its library block and the ordering half of
`TM-M065` go: the options section comes before every colour.

## Part 2: `PrintPage` with switches (`ext.printpage`)

```py
page = PrintPage(width=Length("105mm"), height=Length("148mm"), bleed=Length("3mm"), overflow=Length("7mm"),
                 margin=Sides(top=Length("3mm"), right=Length("7mm"), bottom=Length("10mm"), left=Length("7mm")),
                 marks=True)
page.declare(pkg, full=crop, landscape=pkg.option("landscape", flag=False))
```

- `full=` is the flag that chooses the full sheet, else the trim alone (`Sheet.TRIM`); `landscape=` the flag that turns
  the trim. Either may be left out: that choice is then fixed, as today (`sheet=`).
- `marks=True` adds `showcrop` to the full sheet's geometry.
- Every combination is computed in Python, as now, and written as numbers in up to four `\if` branches, each with its
  `\geometry{...}` and `\pdfvariable pageattr{...}`. Nothing is computed by TeX. Landscape turns the trim and its
  margins together, for symmetric margins only (decision 3, `TM-M074`).

## Tests

- Unit: the options section's text and order; registration twice (same returns the first, different is `TM-M073`);
  `TM-M072`; a document's option settings in `\usepackage[...]`; `ColourSpace` through `option`; each page branch's
  geometry and boxes.
- Compile (`tex`): a synthetic card package with both switches, built four ways; `/TrimBox`, `/BleedBox` and `/MediaBox`
  read back with pikepdf; `\textwidth` and `\textheight` equal on both sheets; crop marks on the full sheet only.
  `showcrop` with `layoutoffset` is measured first (the plan's D1d: its offset forced the consumer's calibration).

**Output change:** a package with a `ColourSpace` renders a different `.sty` (its option moves into the options section
and becomes a key), so a minor release with an `Output change:` line. A `PrintPage` without switches renders as now.

## Open decisions

**2. One flag for the sheet and the marks** (decided): `nocrop` changes the three together: the sheet is the trim alone
(no bleed, no crop margin), the page boxes follow it, and the crop marks go. A `marks` flag of its own can come later
without breaking it.

**3. Margins in landscape** (decided): `landscape` turns the sheet 90°, and the margins turn with it: the portrait's
left and right margins become the top and bottom, its top and bottom the left and right. The type area is the portrait
one turned (91 × 135 mm becomes 135 × 91 mm). This assumes a card's margins are symmetric, top equal to bottom and left
equal to right, so the direction of the turn does not matter. The assumption is checked: a `PrintPage` with a
`landscape` switch and asymmetric margins is refused (`TM-M074`), and that refusal is the signal to reconsider.
The consumer's print sheet measures top 3 mm and bottom 10 mm, but that is not a requirement (their reply, 2026-10-29):
it falls out of their `geometry` call, which they cannot explain either ("does not follow from this option list"), and
their one fixed requirement is the type area. Symmetric margins keep it exactly: left and right 7 mm (105 − 14 = 91),
top and bottom 6.5 mm (148 − 13 = 135), so the same line breaks, with the type area 3.5 mm lower on the print sheet than
today and 5 mm lower on the preview. Nobody has designed a landscape card yet, so turning the margins changes no layout
in use. The compile tests measure `showcrop` with `layoutoffset` first: an offset of that kind is the likely source of
their asymmetry.

`geometry`'s own `landscape` key is not this: it swaps the paper's width and height and applies the margins as written,
on the new edges (measured: 134 × 92 mm here). `PrintPage` writes the turned margins into `geometry` itself.

**Mirrored backs (`twoside`): not needed.** A back is its own page with its front's geometry, for every deck and card
type (their reply).

**5. A document's option setting goes into `\usepackage[...]`** (decided): one way for a document to set any value,
and texmodel puts it where it works. The alternative is a separate `Document(package_options=...)`, which asks the author
to know which values are options.

**6. Only flags, lengths and choices as options** (decided). An integer is the next candidate if a build needs one.

## Steps, once decided

The consumer agreed the margins (`Sides(horizontal=7mm, vertical=6.5mm)`, 91 × 135 mm) and landscape turning them
(2026-10-29). Coming from them: a check that the lower type area moves nothing their printer reads, a landscape card
compiled with today's setup to compare against, and `page.tex`, `boxes.tex` and `options.tex` attached to that reply.

1. Package options and `ColourSpace` moved onto them (core; touches `package.py`, alone).
2. Document settings of options in `\usepackage[...]`.
3. `PrintPage` switches and `marks`.
4. The compile tests; first read the consumer's three files against the design (they stay out of the repo).
5. Guide (`print.md`, `values.md`, `documents.md`), known limitations, the plan's decisions log, the changelog with its
   `Output change:` line.
