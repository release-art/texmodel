# Brief: `Value[T]` slice

You are working in `/Users/ilo/Devel/Release.art/texmodel`, a Python 3.15 monorepo with two packages: `texmodel` (`src/`, the
rendering core, never spawns a process) and `texmodel-build` (`harness/`, optional compile/verify side; leave it alone). Read
first: `README.md`, `CONTRIBUTING.md`, `docs/texmodel-plan.md` (sections 3, 4, 6 and 18; requirement ids M1a, M6, M8, M14, T2,
T4, T5, G1, G2), then `src/texmodel/{components,package,types,drift,config,cli}.py` and `src/texmodel/_internal/render.py`.
Tests: `tests/test_texmodel/`, fixture package `tests/fixtures/acme_cards/` with golden `generated/acme-cards.sty`.

## Goal

Add typed settings to the rendering core: `Value[T]` components for `Length`, `Colour` and `Bool`, rendered into the same
`.sty` as commands and usable from command bodies. A user writes:

```python
@pkg.value
class FactGap(Value[Length]):
    """Space under each fact."""
    default = Length("2mm")

@pkg.value
class Ink(Value[Colour]):
    """The text colour."""
    default = CMYK(0, 0, 0, 0.95)

@pkg.value
class Compact(Value[Bool]):
    """Tighten the layout."""
    default = False
```

## Rendering (the type decides the declaration)

- `Length`: `\newlength{\acFactGap}` then `\setlength{\acFactGap}{2mm}`.
- `Colour`: `\definecolor{ac-ink}{cmyk}{0,0,0,0.95}` (RGB: `{rgb}`, Gray: `{gray}`). The name is `<prefix>-<kebab-case>` (`Ink` ->
  `ac-ink`, `BrandRed` -> `ac-brand-red`). No implicit conversion between colour models.
- `Bool`: `\newif\ifacCompact` and `\acCompactfalse` or `\acCompacttrue` from the default.
- Each package a value needs (colours need `xcolor`) is declared on the component as data (`needs_packages`), the package's
  required set is the pure union over its components, and the `.sty` emits exactly those `\RequirePackage` lines once, sorted,
  after `\ProvidesPackage`. Never collect by mutating anything (plan M14).
- Declaration order is output order; commands and values keep the order they were registered in.
- Keep the existing provenance comment per component (`% from module.Class (...)`) and the docstring comment block.

## Types (`texmodel/types.py`)

- `Length`: frozen, parses `"2mm"`, `"1.5pt"`; units `mm cm in pt bp pc em ex`; stable formatting (`Length("2.0mm")` and
  `Length("2mm")` render the same, no trailing zeros); `float` or `str` input; non-finite, unitless and unknown units are
  refused. Property-test it (hypothesis is fine to add as a dev dependency): parse/format round trip, and unit conversion
  `pt` = 1/72.27 in, `bp` = 1/72 in. Do not convert units on render; keep what the author wrote, normalised.
- `Colour`: `CMYK(c, m, y, k)`, `RGB(r, g, b)`, `Gray(g)`, components in `[0, 1]`, refused outside it. Stable formatting.
- `Bool` is just `bool`.
- Field types for commands stay `Text` / `Text | None`; do not widen them in this slice.

## Lints (plan M8, G2)

- Every control sequence in a body that starts with the package prefix and a capital (`\acFactGap`, `\acFact`) must be a
  declared command or value of the package; an unknown one is a `DeclarationError` naming the class and the name, raised when
  the package is imported (when the last component is registered is too early; check at `render()`/`files()` and in
  `texmodel check`, or add an explicit `pkg.finalize()`, but pick one and document why). Do not flag `\ac@internal` or names
  without the prefix.
- Name collisions across commands and values stay an error at registration (M7). Colour names and control sequences live in
  different namespaces; only collide within each.
- A `Value` needs a `default` of the right type (checked when the class is defined); no default, wrong type, or a class that
  is not `Value[Length|Colour|Bool]` is a `DeclarationError` with a stable `TM-M0xx` code. Pick unused codes and keep them
  stable. Class names obey the existing control-word rule.

## Out of scope

`Int`/counters, scoped overrides (`Set(...)`), colour variants for screen vs print, provenance on colour values, `Environment`,
`Doc` trees, schema export. Do not touch `harness/` except to extend `tests/test_texmodel_build/test_compile_tex.py`.

## Done when

1. `tests/fixtures/acme_cards` gains one `Length`, one `Colour` and one `Bool` value and a command body that uses them; its
   committed golden `generated/acme-cards.sty` is regenerated (command in `CONTRIBUTING.md`) and the diff reviewed by you.
2. `texmodel build` / `texmodel check` work unchanged for it.
3. Container test (marker `tex`, in `tests/test_texmodel_build/test_compile_tex.py`): a document that loads the generated
   `.sty` and uses all three kinds compiles with no errors, and the built PDF's colour operators prove the CMYK colour is CMYK
   (e.g. `0 0 0 0.95 k` in the page content stream; use `pikepdf`, it is installed). Run with
   `TEXMODEL_REQUIRE_TEX=1 pdm run pytest -m tex --no-cov` (needs Docker; the image defaults to
   `releaseart/lualatex-python:latest`, override with `TEXMODEL_TEST_IMAGE`).
4. All of these pass, with no new warnings: `pdm run ruff format --check src harness tests`, `pdm run ruff check src harness
   tests`, `pdm run pyright` (strict on `src` and `harness/src`), `pdm run lint-imports`, `pdm run pytest` (100% coverage gate
   across both packages), `pdm run pip-audit`.
5. README example, `CHANGELOG.md` (`## [Unreleased]`) and the public-API list in `tests/test_texmodel/test_public_api.py`
   (a new top-level module is a deliberate API decision) are updated.

## Conventions and traps

- Code reads like its neighbours: short docstrings that cite plan ids, `DeclarationError(msg, code=, path=, hint=)` for every
  refusal, no printing from the library, no `Any` in public signatures, frozen dataclasses.
- `dataclass_transform` + `__init_subclass__` is how `Command` becomes a dataclass; a generic `Value[T]` base must keep
  `pyright --strict` happy, so the default's type has to be visible to the checker (`default: ClassVar[T]`).
- Python 3.15 has lazy annotations: use `typing.get_type_hints` / `inspect.get_annotations` as `components.py` does; a dataclass
  with no docstring gets an auto-generated `__doc__`, so read the docstring before the decorator runs.
- `.gitignore` ignores `*.log` and `build/`; fixtures that must be committed need an explicit negation.
- Line length 120; ruff selects A, B, C, E, F, I, W, N, C4, T20, PTH; `import texmodel_build` from `src/` is forbidden.
- The golden `.sty` is a contract (plan G7): any change to existing output other than the additions here is a mistake.
- Do not commit, push, or touch GitHub settings. Report what you changed, what you verified and what you could not.
