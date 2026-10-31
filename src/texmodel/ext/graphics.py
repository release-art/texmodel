r"""graphics: pictures that never distort, always say what they show, and sit in a captioned figure.

A `Picture` is `\includegraphics` with opinions. It sets a width, a height or a scale, never two kinds at once; with a
width and a height it fits the picture into that box and keeps its proportions. It needs `alt`, the text a tagged PDF
and a screen reader give for it, or `decorative=True` for a picture that says nothing. `Figure` puts one in a float,
centred, the caption below and the label after it.

```python
picture = Picture("img/logo.png", width=Length.expr(r"0.8\linewidth"), alt="The logo: a blue wave")
Document(Figure(picture, caption="The logo", label="fig:logo").node())
```

The document's package requires `graphicx` (`std.graphicx`); a cropped picture is `crop=Crop(left=Length("2mm"))`.
"""

import dataclasses
from pathlib import PurePosixPath

from ..components import Passthrough
from ..errors import DeclarationError
from ..std import latex
from ..std.graphicx import IncludeGraphics, IncludeGraphicsOptions
from ..types import FilePath, Length, Macro, Name, Raw

_ZERO = Length("0pt")


@dataclasses.dataclass(frozen=True)
class Crop:
    """What is cut off each edge of a picture."""

    left: Length = _ZERO
    bottom: Length = _ZERO
    right: Length = _ZERO
    top: Length = _ZERO


@dataclasses.dataclass(frozen=True)
class Picture:
    """A picture by its path. `width` and `height` are lengths (`Length.expr(r"\\linewidth")` for a share of the line):
    both fit the picture in that box, keeping its proportions; `scale` is a factor and excludes them. `rotate` is
    degrees counter-clockwise, `page` a page of a PDF. The path is a name TeX reads as it is (`TM-C028`), or a
    `Macro`."""

    path: str | PurePosixPath | FilePath | Macro
    _: dataclasses.KW_ONLY
    alt: str | None = None
    decorative: bool = False
    width: Length | None = None
    height: Length | None = None
    scale: float | None = None
    crop: Crop | None = None
    rotate: float | None = None
    page: int | None = None

    def __post_init__(self) -> None:
        if (self.alt is None) == (not self.decorative):
            raise DeclarationError(
                f"Picture({self.path!r}): give alt= or decorative=True, not both and not neither",
                code="TM-M089",
                path=str(self.path),
                hint="alt is the text for a reader who cannot see the picture; decorative=True says there is none",
            )
        if self.scale is not None and (self.width or self.height):
            raise DeclarationError(
                f"Picture({self.path!r}): scale excludes width and height", code="TM-M090", path=str(self.path)
            )

    def node(self) -> IncludeGraphics:
        path = self.path
        if isinstance(path, str):
            path = FilePath(path)
        elif isinstance(path, PurePosixPath):
            path = FilePath.of(path)
        crop = self.crop
        options = IncludeGraphicsOptions(
            width=self.width,
            height=self.height,
            keepaspectratio=bool(self.width and self.height),
            scale=self.scale,
            angle=self.rotate,
            page=self.page,
            clip=crop is not None,
            trim=Raw(" ".join(str(x) for x in (crop.left, crop.bottom, crop.right, crop.top))) if crop else None,
            alt=self.alt,
            artifact=self.decorative,
        )
        return IncludeGraphics(path=path, options=options)

    def render(self) -> str:
        return self.node().render()


@dataclasses.dataclass(frozen=True)
class Figure:
    """A `figure` float of one picture, centred, with its caption below and its label after it. `short` is the entry
    in the list of figures, `placement` the letters of `h`, `t`, `b`, `p` and `!`."""

    picture: Picture
    _: dataclasses.KW_ONLY
    caption: str | None = None
    short: str | None = None
    label: str | None = None
    placement: str | None = None

    def __post_init__(self) -> None:
        if self.placement is not None and not (self.placement and set(self.placement) <= set("htbp!")):
            raise DeclarationError(
                f"Figure: placement {self.placement!r} is not letters of h, t, b, p and !", code="TM-M091"
            )

    def node(self) -> latex.Figure:
        parts = [latex.Centering().render(), self.picture.render()]
        if self.caption is not None:
            parts.append(latex.Caption(short=self.short, text=self.caption).render())
        if self.label is not None:
            parts.append(latex.Label(name=Name(self.label)).render())
        placement = Raw(self.placement) if self.placement else None
        return latex.Figure(Passthrough(Raw("\n".join(parts))), placement=placement)

    def render(self) -> str:
        return self.node().render()


__all__ = ["Crop", "Figure", "Picture"]
