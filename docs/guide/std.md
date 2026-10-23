# Standard libraries

`texmodel.std` has a typed header for each TeX package a deck loads: `latex` (the kernel), `graphicx`, `xcolor`, `geometry`,
`etoolbox`, `eso_pic`, `microtype`, `hyphenat`, `anyfontsize`, `calc`, `pdfrender`, `enumitem`, `adjustbox`, `tikz`,
`tcolorbox` and `fontspec`. The blocks on this page run in order, as one module.

A header is an adopted package with no prefix, whose components name their TeX command with `cs`:

```py
class IncludeGraphics(Command):
    r"""Place a picture: `\includegraphics[width=3cm]{a.png}`."""

    cs = "includegraphics"
    path: Raw
    options: IncludeGraphicsOptions | None = None    # a KeyVals: TeX's one optional argument, written first
```

## Using a header

A body that calls a header's component makes the generated `.sty` load that package. The kernel header (`builtin=True`)
never does.

```python
from texmodel.body import Hole
from texmodel.components import Command
from texmodel.package import Package
from texmodel.std.graphicx import IncludeGraphics, IncludeGraphicsOptions
from texmodel.types import Length, Raw

pkg = Package("figures", prefix="fg")


@pkg.command
class Figure(Command):
    """A full-width picture."""

    path: Raw

    def body(self):
        yield IncludeGraphics.call(
            Hole("path"), options=IncludeGraphicsOptions(width=Length.expr(r"\linewidth"))
        )


assert r"\RequirePackage{graphicx}" in pkg.render()
```

A library whose commands no body calls, or that takes options, is loaded with `pkg.require`, before the packages the bodies
need:

```python
from texmodel.std import microtype

pkg.require(microtype.package, options=["protrusion=true"])
assert r"\RequirePackage[protrusion=true]{microtype}" in pkg.render()
```

## What is typed

`adjustbox`, `graphicx`, `geometry`, `tcolorbox` and `tikz` type their key lists. `calc` is a typed expression language:
`dimen(Length("2cm")) * real(0.5) + widthof("abc")`, with `maxof`, `minof`, `ratio`, `glue`, `integer` and `counter_value`.
The kernel types `\vspace*`, `\makebox`, `\raisebox` and the sectioning commands. A library's own syntax (TikZ paths such
as `\draw (0,0) -- (1,1);`) is written as `Passthrough` or `Raw`.

`tests/test_std` compiles a call of every declared name against the reference image, so a header that names a command TeX
does not have fails, with the path of the call.
