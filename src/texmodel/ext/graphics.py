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
import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any, Final, Self

from .._internal.read import read_length, unescaped
from ..components import Passthrough
from ..errors import DeclarationError, ValidationError
from ..interface import AsTeX
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


def _file(path: "str | PurePosixPath | FilePath | Macro") -> FilePath | Macro:
    if isinstance(path, str):
        return FilePath(path)
    return FilePath.of(path) if isinstance(path, PurePosixPath) else path


@dataclasses.dataclass(frozen=True)
class Picture(AsTeX):
    """A picture by its path. `width` and `height` are lengths (`Length.expr(r"\\linewidth")` for a share of the line):
    both fit the picture in that box, keeping its proportions; `scale` is a factor and excludes them. `rotate` is
    degrees counter-clockwise, `page` a page of a PDF. The path is a name TeX reads as it is (`TM-C028`), or a
    `Macro`. A `Picture` is a value a command field takes (`AsTeX`): `icon: Icon | Picture | None`."""

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
        _file(self.path)  # a path TeX would read as syntax is refused here, not when it is rendered
        if (self.alt is None) == (not self.decorative):
            raise ValidationError(
                f"Picture({self.path!r}): give alt= or decorative=True, not both and not neither",
                code="TM-C033",
                path=str(self.path),
                hint="alt is the text for a reader who cannot see the picture; decorative=True says there is none",
            )
        if self.scale is not None and (self.width or self.height):
            raise ValidationError(
                f"Picture({self.path!r}): scale excludes width and height", code="TM-C034", path=str(self.path)
            )

    def node(self) -> IncludeGraphics:
        path, crop = _file(self.path), self.crop
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

    @classmethod
    def read(cls, text: str) -> Self:
        r"""A picture from the `\includegraphics` call it was written as (what a stub shows of a field), so a hand edit
        of it is seen. A call with a key it does not write, or a path from a macro, is not read."""
        body = text.strip()
        if body.startswith("{") and body.endswith("}"):  # the group a key list puts around a value
            body = body[1:-1].strip()
        call = _CALL.fullmatch(body)
        if not call:
            raise ValueError(f"{body!r} is not an \\includegraphics call")
        if "\\" in call["path"]:
            raise NotImplementedError("a path from a macro")
        given: dict[str, Any] = {}
        for key, value in _keys(call["keys"] or ""):
            if key in _WRITTEN_WITH_OTHERS:
                continue
            if key in _FLAGS and value is None:
                given[_FLAGS[key]] = True
            elif key in _READERS and value is not None:
                name, read = _READERS[key]
                given[name] = read(value)
            else:
                raise ValueError(f"{key!r} is not a key of a Picture, or has no value")
        try:
            return cls(call["path"].strip(), **given)
        except (ValidationError, DeclarationError) as exc:
            raise ValueError(str(exc)) from exc


def _crop(text: str) -> Crop:
    left, bottom, right, top = (read_length(p) for p in text.split())
    return Crop(left, bottom, right, top)


_READERS: Final[dict[str, tuple[str, Callable[[str], object]]]] = {
    "width": ("width", read_length),
    "height": ("height", read_length),
    "scale": ("scale", float),
    "angle": ("rotate", float),
    "page": ("page", int),
    "alt": ("alt", unescaped),
    "trim": ("crop", _crop),
}
_FLAGS: Final = {"artifact": "decorative"}
_WRITTEN_WITH_OTHERS: Final = {"clip", "keepaspectratio"}  # the crop and the box say them
_CALL: Final = re.compile(r"\\includegraphics\s*(?:\[(?P<keys>.*)\])?\s*\{(?P<path>[^{}]*)\}", re.DOTALL)


def _keys(text: str) -> list[tuple[str, str | None]]:
    """`width=3cm,alt={a, b},clip` as pairs, split at the commas outside braces; a bare key has no value, a braced value
    loses its braces."""
    parts: list[str] = []
    depth, start = 0, 0
    for i, c in enumerate(text + ","):
        depth += (c == "{") - (c == "}")
        if c == "," and depth == 0:
            parts.append(text[start:i].strip())
            start = i + 1
    pairs: list[tuple[str, str | None]] = []
    for part in filter(None, parts):
        key, equals, value = part.partition("=")
        value = value.strip()
        braced = value.startswith("{") and value.endswith("}")
        pairs.append((key.strip(), (value[1:-1] if braced else value) if equals else None))
    return pairs


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
            raise ValidationError(
                f"Figure: placement {self.placement!r} is not letters of h, t, b, p and !", code="TM-C035"
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
