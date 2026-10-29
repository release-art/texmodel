r"""spot: a named plate on the press (a varnish, a foil, a Pantone) with a CMYK proxy, and tints of it.

`Spot("Scodix", proxy=K(1))` is `/Separation /Scodix /DeviceCMYK`: the press reads the plate name, and a viewer that
does not render the plate shows the proxy. `Value[SpotColour]` declares one (`\definespotcolor`, from `colorspace`: the
`spotcolor` package is pdfTeX-only) and `tint(Varnish, 0.6)` is xcolor's `ap-varnish!60`. A plate is registered once, so
a spot value is declared and tinted, never set by a document (`TM-M055`).

```python
class Varnish(Value[SpotColour]):
    '''Spot-UV varnish.'''

    default = Spot("Scodix", proxy=K(1))
```
"""

import dataclasses
import re
import typing
from typing import Annotated, Any

from pydantic_core import core_schema as cs

from .._internal.render import COLOUR, colour_name
from ..components import Value
from ..errors import DeclarationError
from ..types import CMYK, plain_number
from .colourspace import colour_of
from .kplate import K

# A PDF name ends at a delimiter, and TeX reads `%` `#` `\` `{` `}`: any of them in a plate name writes a file whose
# name is cut in two (qpdf: "expected dictionary key"), or no file at all. Spaces and non-ASCII are written escaped.
_UNSAFE = re.compile(r"[/()<>\[\]{}%#\\\x00-\x1f\x7f]")


@dataclasses.dataclass(frozen=True)
class Spot:
    """A plate and its proxy: `plate` is the separation's name as the press reads it, `proxy` the process colour a
    viewer shows in its place."""

    plate: str
    proxy: CMYK = K(1)

    def __post_init__(self) -> None:
        if not isinstance(self.proxy, K) and self.proxy.c == self.proxy.m == self.proxy.y == 0:
            object.__setattr__(self, "proxy", K(self.proxy.k))  # one value for one colour, however it was written
        if not self.plate.strip() or _UNSAFE.search(self.plate):
            raise DeclarationError(
                f"Spot.plate={self.plate!r}: not empty, no `/ ( ) < > [ ] {{ }} % # \\` and no control character",
                code="TM-M053",
                path="plate",
                hint="a PDF name ends at a delimiter; spaces and non-ASCII are fine",
            )

    @classmethod
    def __get_pydantic_core_schema__(cls, source: object, handler: Any) -> cs.CoreSchema:  # noqa: ANN401
        def make(value: object) -> "Spot":
            if isinstance(value, Spot):
                return value
            try:
                data = typing.cast("dict[str, Any]", dict(typing.cast("Any", value)))
                return cls(str(data["plate"]), CMYK(*map(float, data["proxy"])))
            except (DeclarationError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(str(exc)) from exc

        def dump(spot: "Spot") -> dict[str, object]:
            return {"plate": spot.plate, "proxy": [spot.proxy.c, spot.proxy.m, spot.proxy.y, spot.proxy.k]}

        shape = cs.typed_dict_schema(
            {
                "plate": cs.typed_dict_field(cs.str_schema(min_length=1)),
                "proxy": cs.typed_dict_field(cs.list_schema(cs.float_schema(ge=0, le=1), min_length=4, max_length=4)),
            }
        )
        return cs.json_or_python_schema(
            json_schema=cs.chain_schema([shape, cs.no_info_plain_validator_function(make)]),
            python_schema=cs.no_info_plain_validator_function(make),
            serialization=cs.plain_serializer_function_ser_schema(dump),
        )


def _line(prefix: str, name: str, value: Any, alias: str | None) -> str:  # noqa: ANN401
    return f"\\definespotcolor{{{alias or colour_name(prefix, name)}}}{{{value.plate}}}{{{value.proxy}}}"


def _no_setting(prefix: str, name: str, value: Any, alias: str | None) -> str:  # noqa: ANN401
    raise DeclarationError(
        f"{alias or colour_name(prefix, name)}: a spot colour is declared once and is not a setting",
        code="TM-M055",
        path=name,
        hint="colorspace stops on a plate defined twice (`Duplicated spot name`)",
    )


def _declare(prefix: str, name: str, default: Any, alias: str | None) -> list[str]:  # noqa: ANN401
    return [] if default is None else [_line(prefix, name, default, alias)]


KIND = dataclasses.replace(
    COLOUR,
    name="Spot",
    python=Spot,
    json_type="object",
    declare=_declare,
    setting=_no_setting,
    needs=("xcolor", "colorspace"),  # tints are xcolor's; `\definespotcolor` is colorspace's
)
SpotColour = Annotated[Spot, KIND]
"""`Value[SpotColour]`: a spot colour; its default, and every setting, is a `Spot`."""


def tint(value: type[Value[Any]], fraction: float) -> str:
    """xcolor's tint of a `Value[SpotColour]` toward white: `tint(Varnish, 0.6)` is `ap-varnish!60`."""
    if getattr(value, "__tm_kind__", None) is not KIND:
        raise DeclarationError(
            f"tint({value.__name__}): not a Value[SpotColour]",
            code="TM-M054",
            path=value.__name__,
            hint="declare it as Value[SpotColour] with a Spot default",
        )
    if not 0 <= fraction <= 1:
        raise DeclarationError(f"tint({value.__name__}, {fraction!r}): in [0, 1]", code="TM-M017", path=value.__name__)
    return f"{colour_of(value)}!{plain_number(fraction * 100)}"


__all__ = ["KIND", "Spot", "SpotColour", "tint"]
