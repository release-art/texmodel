r"""printpage: a print page (trim, bleed, crop margin) as one declaration: its geometry and its PDF page boxes.

A printer trims to `/TrimBox` and lets artwork run to `/BleedBox`; PDF/X requires only that both exist and nest, so a
file can be valid and trimmed to the wrong size. `PrintPage` derives both from the trim, the bleed and the margin
around the trim, edge by edge. All of it is numbers in the generated `.sty`: nothing is computed by TeX.

The page is fixed when the package is generated: one sheet, which no package option switches (a crop build and a
preview build, or landscape), and no crop marks. A page chosen when TeX loads the package keeps its own geometry.

```python
page = PrintPage(
    width=Length("105mm"), height=Length("138mm"),     # the trim
    bleed=Length("3mm"),                               # or Sides(all=Length("3mm"), left=Length("0mm"))
    overflow=Length("7mm"),                            # room for marks outside the trim; default: the bleed
    margin=Sides(horizontal=Length("7mm"), vertical=Length("1.5mm")),   # trim to type area
)
page.declare(pkg)
```
"""

import dataclasses
import enum
from fractions import Fraction
from typing import overload

from ..errors import DeclarationError
from ..package import Package
from ..types import Length, Raw, plain_number

LIBRARY = r"""
    \ifdefined\pdfvariable\else
      \PackageError{<<package>>}{lualatex required}%
        {The page boxes are written with luaTeX's \string\pdfvariable\space pageattr.}%
    \fi
    \RequirePackage{geometry}
    \geometry{<<geometry>>}
    \pdfvariable pageattr{<<boxes>>}
"""

_SIDES = ("top", "right", "bottom", "left")


@dataclasses.dataclass(frozen=True, init=False)
class Sides:
    """A length for each edge: `Sides(all=Length("3mm"))`, `Sides(horizontal=, vertical=)` or the four edges, and any
    edge after `all=` or `horizontal=`/`vertical=` replaces that edge (`Sides(all=Length("3mm"), left=Length("0mm"))`).
    Every edge must come out with a length (`TM-M051`); `all=` and `horizontal=`/`vertical=` do not mix."""

    top: Length
    right: Length
    bottom: Length
    left: Length

    @overload
    def __init__(
        self,
        *,
        all: Length,  # noqa: A002  # the name CSS gives it
        top: Length | None = None,
        right: Length | None = None,
        bottom: Length | None = None,
        left: Length | None = None,
    ) -> None: ...
    @overload
    def __init__(
        self,
        *,
        horizontal: Length,
        vertical: Length,
        top: Length | None = None,
        right: Length | None = None,
        bottom: Length | None = None,
        left: Length | None = None,
    ) -> None: ...
    @overload
    def __init__(self, *, top: Length, right: Length, bottom: Length, left: Length) -> None: ...
    def __init__(
        self,
        *,
        all: Length | None = None,  # noqa: A002
        horizontal: Length | None = None,
        vertical: Length | None = None,
        top: Length | None = None,
        right: Length | None = None,
        bottom: Length | None = None,
        left: Length | None = None,
    ) -> None:
        if all is not None and (horizontal is not None or vertical is not None):
            raise DeclarationError(
                "Sides: all= with horizontal= or vertical= says two things for the same edge",
                code="TM-M051",
                hint="all= alone, or horizontal= and vertical=; name an edge to replace it",
            )
        base = {
            "top": vertical if all is None else all,
            "bottom": vertical if all is None else all,
            "left": horizontal if all is None else all,
            "right": horizontal if all is None else all,
        }
        given = {"top": top, "right": right, "bottom": bottom, "left": left}
        resolved = {edge: given[edge] if given[edge] is not None else base[edge] for edge in _SIDES}
        if missing := [edge for edge, v in resolved.items() if v is None]:
            raise DeclarationError(
                f"Sides: no length for {', '.join(missing)}",
                code="TM-M051",
                hint="all=, horizontal= with vertical=, or every edge",
            )
        for edge, value in resolved.items():
            object.__setattr__(self, edge, value)

    def inches(self) -> tuple[Fraction, Fraction, Fraction, Fraction]:
        """The exact sizes `(top, right, bottom, left)`; a length relative to the font or a TeX expression has none."""
        return (self.top.inches, self.right.inches, self.bottom.inches, self.left.inches)


@enum.unique
class Sheet(enum.Enum):
    """What a build puts on the sheet: `FULL` is the trim with its margin (what the printer gets); `TRIM` is the trim
    alone, a review copy whose type area is the same."""

    FULL = "full"
    TRIM = "trim"


def _sides(value: "Length | Sides") -> Sides:
    return value if isinstance(value, Sides) else Sides(all=value)


def _mm(inches: Fraction) -> str:
    return f"{plain_number(float(inches * Fraction(254, 10)))}mm"


def _bp(inches: Fraction) -> str:
    return plain_number(float(inches * 72))


@dataclasses.dataclass(frozen=True, init=False)
class PrintPage:
    """A print page: the trim `width` by `height`, `bleed` past it, `overflow` (at least the bleed) of sheet around it
    for marks, and `margin` from the trim to the type area. Each of the three is a `Length` for every edge or `Sides`.
    The geometry and the page boxes are written for `sheet`."""

    width: Length
    height: Length
    bleed: Sides
    overflow: Sides
    margin: Sides
    sheet: Sheet

    def __init__(
        self,
        *,
        width: Length,
        height: Length,
        bleed: Length | Sides,
        overflow: Length | Sides | None = None,
        margin: Length | Sides | None = None,
        sheet: Sheet = Sheet.FULL,
    ) -> None:
        bleeds = _sides(bleed)
        overflows = bleeds if overflow is None else _sides(overflow)
        for edge, b, o in zip(_SIDES, bleeds.inches(), overflows.inches(), strict=True):
            if o < b:
                raise DeclarationError(
                    f"PrintPage: the {edge} overflow is less than the bleed", code="TM-M052", path=edge
                )
        for name, value in (("width", width), ("height", height)):
            if value.inches <= 0:
                raise DeclarationError(f"PrintPage.{name}={value}: a size", code="TM-M052", path=name)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "bleed", bleeds)
        object.__setattr__(self, "overflow", overflows)
        object.__setattr__(self, "margin", _sides(Length("0mm")) if margin is None else _sides(margin))
        object.__setattr__(self, "sheet", sheet)

    def _extent(self) -> tuple[Fraction, Fraction, Fraction, Fraction, Fraction, Fraction]:
        """The trim size, then each edge's overflow (none for `TRIM`): `(w, h, top, right, bottom, left)` in inches."""
        zero = (Fraction(0),) * 4
        top, right, bottom, left = zero if self.sheet is Sheet.TRIM else self.overflow.inches()
        return (self.width.inches, self.height.inches, top, right, bottom, left)

    def geometry(self) -> str:
        """The keys of `\\geometry{}`: the paper, where the trim sits on it, and the type area, which is the same in
        both sheets."""
        w, h, top, right, bottom, left = self._extent()
        mt, mr, mb, ml = (_mm(x) for x in self.margin.inches())
        keys = [f"papersize={{{_mm(w + left + right)},{_mm(h + top + bottom)}}}"]
        if self.sheet is Sheet.FULL:
            keys += [f"layoutsize={{{_mm(w)},{_mm(h)}}}", f"layoutoffset={{{_mm(left)},{_mm(top)}}}"]
        keys += [f"left={ml}", f"right={mr}", f"top={mt}", f"bottom={mb}"]
        return ",".join([*keys, "nohead", "nofoot", "headheight=0pt", "headsep=0pt", "footskip=0pt"])

    def boxes(self) -> str:
        """The page boxes in bp, from the lower left of the media; `/MediaBox` is the engine's own, and a second one
        would be a duplicate key in every page dictionary."""
        w, h, top, right, bottom, left = self._extent()
        bt, br, bb, bl = (Fraction(0),) * 4 if self.sheet is Sheet.TRIM else self.bleed.inches()
        media = f"[0 0 {_bp(w + left + right)} {_bp(h + top + bottom)}]"
        bleed = f"[{_bp(left - bl)} {_bp(bottom - bb)} {_bp(left + w + br)} {_bp(bottom + h + bt)}]"
        trim = f"[{_bp(left)} {_bp(bottom)} {_bp(left + w)} {_bp(bottom + h)}]"
        return f"/CropBox {media}/BleedBox {bleed}/TrimBox {trim}"

    def declare(self, package: Package) -> None:
        """The geometry and the page boxes, as a block of the package's `.sty`, `print-page`."""
        package.library(
            "print-page",
            LIBRARY,
            fill={"package": Raw(package.name), "geometry": Raw(self.geometry()), "boxes": Raw(self.boxes())},
        )


__all__ = ["LIBRARY", "PrintPage", "Sheet", "Sides"]
