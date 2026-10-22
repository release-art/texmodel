# Known limitations

What texmodel does not do or does not check today. Planned work is in [the plan](texmodel-plan.md) (§19, §21a).

## Scope

- No TeX parser (plan N1). Interfaces are declared, never read back from TeX texmodel did not write. The adoption scanner
  (`check_interface`) reads `\newcommand`, `\providecommand`, `\newenvironment` and the xparse `\NewDocumentCommand` family;
  a name defined another way counts as missing, and an xparse type it does not model (`v`, `u`, `g`, `e`) is reported as
  `?` and matches nothing.
- Python 3.15 and LuaLaTeX only. Compiling needs the reference image (or a local TeX Live with `latexmk`).
- Not built: release migrations, `Doc` trees from data with migrations, trust levels and the injection corpus, the
  sandbox verification, `texmodel-print`, a rules layer, `List[T]` settings (`Value[...]` takes `Length`, `Colour`, `bool`,
  `Text`, `Raw`).
- No check of what TeX would do with a value: a `Length` key is checked to be a length, not to be sensible for the package.
  Layout is not checked at all; `Overset` types a package's own "does not fit" warning.

## Arguments and key lists

- A definition needs LaTeX 2020-10 or later when its signature is not `\newcommand`-shaped (xparse is in the kernel from
  then). Hole numbers are `#1`...`#9`; a signature with more slots is not refused by texmodel, TeX refuses it.
- A `Hole` stands for a whole argument. It cannot sit inside a `KeyVals` or a tuple; build the list in the body with
  `Raw` pieces instead.
- Verbatim and delimited-by-token arguments are not modelled. Neither is an optional braced group (xparse `g`).
- A colour model (`CMYK`, `RGB`, `Gray`) writes its components, `0,0,0,1`, which suits `\definecolor` and
  `\color[cmyk]{...}`; a macro that wants a name takes `ColourName`.
- A `KeyVals` that fails its own checks (`exclusive`, `requires`, a wrong type) raises pydantic's `ValidationError` when it
  is built, not a `Violation` from `validate()`.
- Key libraries differ in ways the presets only partly capture. `KeyRules` was measured against pgfkeys, xkeyval, keyval
  and l3keys with a corpus of awkward values (`tests/test_texmodel/test_interface_tex.py`); `KVOPTIONS` was not. A space at
  the end of a value is kept by `{{ a }}` in three of the four and trimmed by `l3keys`; a library that treats braces
  differently from these needs its own `KeyRules`.
- A `Raw` value or `Item[Raw]` is written as given: texmodel checks only that its braces balance.
- The names `content` (an environment's children) and `type` (the component in data) are not usable as field names.

## The standard headers

- `texmodel.std` covers the commands a deck uses, not each package. `adjustbox`, `graphicx`, `geometry`, `tcolorbox` and `tikz`
  type their common keys and take the rest as `Item[Raw]`; the other headers still take `Raw` for options and lengths.
- `calc`: a parenthesised integer expression after `*` or `/` (`2cm*(1+2)`) works in TeX Live 2025's `calc` but is not in its
  documented grammar, which allows only a number, `\real`, `\ratio`, `\maxof` or `\minof` there. The header allows it.
  `\relax` scan stops are not modelled.
- `tests/test_std` proves a call is accepted by TeX, not that it does what the name suggests. A library the reference image
  lacks makes its test skip (a failure under `TEXMODEL_REQUIRE_TEX=1`).
- TikZ paths (`\draw`, `\node`) are written as `Passthrough` or `Raw`.
