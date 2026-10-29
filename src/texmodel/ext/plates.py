r"""plates: the plates a colour inks, and the K-only colour.

A press prints a colour with one or more plates: the process inks C, M, Y and K, or a spot (a varnish, a foil, a
Pantone). Small type set on four plates shows every registration error; on one plate it cannot misregister with itself.
A colour value declares the plates it may ink, and a default, a setting or data outside them is refused:

```python
class Ink(Value[Colour]):
    '''Text ink.'''

    plates = {Plate.K}          # K only; {Plate.C, Plate.M} is a duotone
    default = K(0.95)
```

`K(0.7)` is `0,0,0,0.7`. A tint or a mix (`ColourName`) keeps the plates only when both ends ink the same ones.
Fractions are TeX's: 0 to 1, refused outside it (`TM-M017`).
"""

import dataclasses
from decimal import ROUND_HALF_EVEN, Decimal

from ..errors import DeclarationError
from ..types import CMYK, PROCESS, Plate, plain_number, plates_of


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


__all__ = ["PROCESS", "K", "Plate", "plates_of"]
