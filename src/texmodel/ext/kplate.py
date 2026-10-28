r"""kplate: colours that ink one plate, the black one.

Small type set on four plates shows every registration error; on one plate it cannot misregister with itself.
`K(0.7)` is `0,0,0,0.7` in `cmyk`, `Value[KOnly]` holds only such a colour, and `tint(Ink, 0.7)` is xcolor's
`ac-ink!70`, which keeps the plate because the base has only one. Fractions are TeX's: 0 to 1, refused outside it
(`TM-M017`).

```python
class Ink(Value[KOnly]):
    '''Text ink.'''

    default = K(0.95)
```
"""

import dataclasses
import enum
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated, Any

from pydantic_core import core_schema as cs

from .._internal.render import COLOUR, colour_name
from ..components import Value
from ..errors import DeclarationError
from ..types import CMYK, RGB, Colour, Gray, plain_number


@dataclasses.dataclass(frozen=True, init=False, repr=False)
class K(CMYK):
    """A colour on the black plate only: `K(0.7)` is `0,0,0,0.7`. A `CMYK`, so it goes wherever one does."""

    def __init__(self, k: float) -> None:
        super().__init__(0.0, 0.0, 0.0, k)  # the bounds are `CMYK`'s: [0, 1], TM-M017

    def __repr__(self) -> str:
        return f"K({plain_number(self.k)})"

    @classmethod
    def nearest(cls, k: float, *, step: float = 0.05) -> "K":
        """`k` rounded to a multiple of `step` (a print designer's 5%): `K.nearest(0.68)` is `K(0.7)`."""
        if not 0 < step <= 1:
            raise DeclarationError(f"K.nearest: step {step!r} must be in (0, 1]", code="TM-M046", path="step")
        unit = Decimal(str(step))
        return cls(float((Decimal(str(k)) / unit).to_integral_value(ROUND_HALF_EVEN) * unit))

    @classmethod
    def __get_pydantic_core_schema__(cls, source: object, handler: Any) -> cs.CoreSchema:  # noqa: ANN401
        def make(value: object) -> "K":
            if isinstance(value, K):
                return value
            try:
                return cls(float(value))  # pyright: ignore[reportArgumentType]
            except (DeclarationError, TypeError, ValueError) as exc:
                raise ValueError(str(exc)) from exc

        return cs.json_or_python_schema(
            json_schema=cs.chain_schema([cs.float_schema(ge=0, le=1), cs.no_info_plain_validator_function(make)]),
            python_schema=cs.no_info_plain_validator_function(make),
            serialization=cs.plain_serializer_function_ser_schema(lambda colour: colour.k),
        )


KIND = dataclasses.replace(COLOUR, name="K", python=K, json_type="number")
KOnly = Annotated[K, KIND]
"""`Value[KOnly]`: a colour on the black plate only; its default, and every setting, is a `K`."""


@enum.unique
class Plate(enum.StrEnum):
    C = "C"
    M = "M"
    Y = "Y"
    K = "K"


def plates(colour: Colour) -> frozenset[Plate]:
    """The plates a colour inks. A `Gray` is the black plate (white inks none). An `RGB` is converted by the output
    intent, so any plate may carry it: all four."""
    if isinstance(colour, CMYK):
        return frozenset(p for p, v in zip(Plate, (colour.c, colour.m, colour.y, colour.k), strict=True) if v > 0)
    if isinstance(colour, Gray):
        return frozenset({Plate.K}) if colour.g < 1 else frozenset()
    assert isinstance(colour, RGB)
    return frozenset(Plate)


def is_single_plate(colour: Colour) -> bool:
    """Whether the colour inks no more than one plate: `K(0.7)` and `Gray(0.3)` do, a `CMYK` with two inks does not."""
    return len(plates(colour)) <= 1


def tint(value: type[Value[Any]], fraction: float) -> str:
    """xcolor's tint of a `Value[KOnly]` toward white: `tint(Ink, 0.7)` is `acInk!70`. It stays on the black plate
    because the base does; any other colour is refused (`TM-M047`), since its tint is not one plate."""
    if getattr(value, "__tm_kind__", None) is not KIND:
        raise DeclarationError(
            f"tint({value.__name__}): not a Value[KOnly]; a tint of a colour on several plates is not one plate",
            code="TM-M047",
            path=value.__name__,
            hint="declare it as Value[KOnly] with a K default",
        )
    if not 0 <= fraction <= 1:
        raise DeclarationError(f"tint({value.__name__}, {fraction!r}): in [0, 1]", code="TM-M017", path=value.__name__)
    name = value.colour_name or colour_name(value.__tm_prefix__, value.__name__)
    return f"{name}!{plain_number(fraction * 100)}"


__all__ = ["KIND", "K", "KOnly", "Plate", "is_single_plate", "plates", "tint"]
