r"""Headers for the standard TeX libraries a deck loads (one module per package, adopted: the interface only).

Written for TeX Live `TEXLIVE`; `tests/test_std` compiles a call of every command against the reference image.
A header covers what fits the model (required `{}` arguments and one leading `[]`); a library's own syntax
(TikZ paths, key-value declarations) is written as `Passthrough` or `Raw`.

```python
from texmodel.std.graphicx import IncludeGraphics

class Photo(Command):
    '''A picture.'''
    path: Text

    def body(self):
        yield IncludeGraphics.call(Hole("path"), options=Raw("width=\\linewidth"))   # \RequirePackage{graphicx}
```
"""

TEXLIVE = "2025"
MODULES = (
    "latex",
    "graphicx",
    "xcolor",
    "geometry",
    "etoolbox",
    "eso_pic",
    "microtype",
    "hyphenat",
    "anyfontsize",
    "calc",
    "pdfrender",
    "enumitem",
    "adjustbox",
    "tikz",
    "tcolorbox",
    "tabularray",
    "fontspec",
    "hyperref",
    "setspace",
    "fancyhdr",
    "caption",
    "subcaption",
    "babel",
    "polyglossia",
    "multicol",
    "pdfpages",
    "luacolor",
)
