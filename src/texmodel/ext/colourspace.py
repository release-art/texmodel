r"""colourspace: a colour with a print build and a screen build, one name, chosen when the package loads.

A brand that prints and shows on screen states each colour twice: CMYK for print, RGB for screen. `ColourPair` holds
both, and `Value[Dual]` declares it under one xcolor name (`ap-ink`): the CMYK definition when the print build is
in use, the HTML one when not. A document picks the build with a class option (`Document(options=["rgb"])`), which
LaTeX gives to every package that declares it. It is not a conversion between models: both builds are stated.

```python
ColourSpace().declare(pkg)          # before the colours: the options and the flag


class Ink(Value[Dual]):
    '''Text ink.'''

    default = ColourPair(cmyk=K(0.95), rgb="2d2c2b")
```

`colour_of(Ink)` is the xcolor name, for a body or a field: `ColourName(Ink, tint=0.7)` is `ap-ink!70`.
"""

import dataclasses
import enum
import re
import types
import typing
from typing import Annotated, Any

from pydantic_core import core_schema as cs

from .._internal.render import COLOUR, colour_name
from ..components import Value
from ..errors import DeclarationError
from ..interface import colour_of
from ..package import Package
from ..types import CMYK, RGB, Raw

_HEX = re.compile(r"[0-9A-Fa-f]{6}")

LIBRARY = r"""
    \newif\if<<p>>Cmyk
    \<<p>>Cmyk<<default>>
    \DeclareOption{cmyk}{\<<p>>Cmyktrue}
    \DeclareOption{rgb}{\<<p>>Cmykfalse}
    \ProcessOptions\relax
"""


@dataclasses.dataclass(frozen=True)
class ColourPair:
    """A colour's print build and screen build. `cmyk` is a `CMYK` (a `K` is one, kept as a plain `CMYK`); `rgb` is six
    hex digits, or an `RGB` rounded to 8 bits. Either may be `None`: the colour then exists in the other build only,
    and using it in this one is xcolor's undefined-colour error."""

    cmyk: CMYK | None = None
    rgb: str | RGB | None = None

    def __post_init__(self) -> None:
        if self.cmyk is None and self.rgb is None:
            raise DeclarationError("ColourPair: a print build, a screen build, or both", code="TM-M064")
        if self.cmyk is not None and type(self.cmyk) is not CMYK:  # a K is a CMYK: one value for one colour
            object.__setattr__(self, "cmyk", CMYK(self.cmyk.c, self.cmyk.m, self.cmyk.y, self.cmyk.k))
        rgb = self.rgb
        if isinstance(rgb, RGB):
            rgb = "".join(f"{round(x * 255):02X}" for x in (rgb.r, rgb.g, rgb.b))
        if rgb is not None:
            if not _HEX.fullmatch(rgb):
                raise DeclarationError(
                    f"ColourPair.rgb={rgb!r}: six hex digits, such as '2d2c2b'", code="TM-M064", path="rgb"
                )
            object.__setattr__(self, "rgb", rgb.upper())

    @property
    def plates(self) -> frozenset[str]:
        """The plates of its print build: none for a screen-only colour."""
        return frozenset() if self.cmyk is None else self.cmyk.plates

    @classmethod
    def __get_pydantic_core_schema__(cls, source: object, handler: Any) -> cs.CoreSchema:  # noqa: ANN401
        def make(value: object) -> "ColourPair":
            if isinstance(value, ColourPair):
                return value
            try:
                data = typing.cast("dict[str, Any]", dict(typing.cast("Any", value)))
                cmyk = data.get("cmyk")
                return cls(None if cmyk is None else CMYK(*map(float, cmyk)), data.get("rgb"))
            except (DeclarationError, TypeError, ValueError) as exc:
                raise ValueError(str(exc)) from exc

        def dump(pair: "ColourPair") -> dict[str, object]:
            c = pair.cmyk
            return {"cmyk": None if c is None else [c.c, c.m, c.y, c.k], "rgb": pair.rgb}

        shape = cs.typed_dict_schema(
            {
                "cmyk": cs.typed_dict_field(
                    cs.nullable_schema(cs.list_schema(cs.float_schema(ge=0, le=1), min_length=4, max_length=4)),
                    required=False,
                ),
                "rgb": cs.typed_dict_field(cs.nullable_schema(cs.str_schema(pattern=_HEX.pattern)), required=False),
            }
        )
        return cs.json_or_python_schema(
            json_schema=cs.chain_schema([shape, cs.no_info_plain_validator_function(make)]),
            python_schema=cs.no_info_plain_validator_function(make),
            serialization=cs.plain_serializer_function_ser_schema(dump),
        )


def _lines(prefix: str, name: str, value: Any, alias: str | None) -> list[str]:  # noqa: ANN401
    colour = alias or colour_name(prefix, name)
    cmyk = [] if value.cmyk is None else [rf"\definecolor{{{colour}}}{{cmyk}}{{{value.cmyk}}}"]
    rgb = [] if value.rgb is None else [rf"\definecolor{{{colour}}}{{HTML}}{{{value.rgb}}}"]
    return [rf"\if{prefix}Cmyk", *cmyk, r"\else", *rgb, r"\fi"]


def _declare(prefix: str, name: str, default: Any, alias: str | None) -> list[str]:  # noqa: ANN401
    return [] if default is None else _lines(prefix, name, default, alias)


def _setting(prefix: str, name: str, value: Any, alias: str | None) -> str:  # noqa: ANN401
    return "".join(_lines(prefix, name, value, alias))


KIND = dataclasses.replace(
    COLOUR, name="Dual", python=ColourPair, json_type="object", declare=_declare, setting=_setting
)
Dual = Annotated[ColourPair, KIND]
"""`Value[Dual]`: a colour with a print build and a screen build; its default, and every setting, is a `ColourPair`."""


@enum.unique
class Build(enum.Enum):
    """The build a document gets when it names none."""

    CMYK = "cmyk"
    RGB = "rgb"


@dataclasses.dataclass(frozen=True)
class ColourSpace:
    """The `cmyk` and `rgb` package options and the flag `\\if<prefix>Cmyk` the colours test. It processes the
    package's options (`\\ProcessOptions`, once per package), so it is declared before the colours and before any other
    options the package declares."""

    default: Build = Build.CMYK

    def declare(self, package: Package) -> type[Value[Any]]:
        """The block, and the flag as a `Value[bool]` (`\\if<prefix>Cmyk`) that the block defines."""
        if not package.prefix:
            raise DeclarationError("ColourSpace: the package has no prefix", code="TM-M065", path=package.name)
        if any(getattr(c, "__tm_kind__", None) is KIND for c in package.registered):
            raise DeclarationError(
                "ColourSpace: declare it before the colours: the colours test its flag when the package loads",
                code="TM-M065",
                path=package.name,
            )
        lib = package.library(
            "colourspace",
            LIBRARY,
            fill={"p": Raw(package.prefix), "default": Raw("true" if self.default is Build.CMYK else "false")},
        )
        flag = types.new_class(
            "Cmyk",
            (Value[bool],),
            exec_body=lambda ns: ns.update(
                __doc__="Whether the print build of the colours is in use.", __module__=package.name, defined_by=lib
            ),
        )
        return package.value(flag)


__all__ = ["KIND", "Build", "ColourPair", "ColourSpace", "Dual", "colour_of"]
