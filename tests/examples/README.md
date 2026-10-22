# Examples

Each directory is a complete `texmodel` package: the Python declarations, the TeX bodies (inline, or `TemplateRef` files beside them), a `documents`
dict of rendered documents, and `expected/`, the committed output (the golden). `tests/test_texmodel/test_examples.py`
renders every example and compares it with `expected/`, so a change in generated output shows up as a diff here
(plan G7). With `TEXMODEL_REQUIRE_TEX=1 pdm run pytest -m tex`, every golden `.tex` is also compiled.

| Example | Shows |
|---|---|
| `hello` | the smallest package: one command with an inline body, and escaping |
| `business_card` | commands, an optional argument, `Length` / `Colour` / `Bool` values, an environment with a grammar, settings |
| `letter` | environment arguments, nested environments, `Raw`, a value that needs another package, relative units |
| `composed` | one package calling another by `Ref`, with `\RequirePackage` following |
| `expl3` | a verbatim expl3 library block, a component it defines (`defined_by`), and a body written in expl3 |

After an intended change: `UPDATE_GOLDEN=1 pdm run pytest tests/test_texmodel/test_examples.py`, then review the diff.
