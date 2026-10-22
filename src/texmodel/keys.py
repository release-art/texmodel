"""How key libraries read a key list: a `KeyRules` value, and a preset per library.

A `KeyVals` takes one: `class AdjustOptions(KeyVals, rules=PGFKEYS)`. A library that differs is a `dataclasses.replace`
of the nearest preset. What each preset holds is what the compile tests (`tests/test_std`) confirm against the library.
"""

import dataclasses
from typing import Final

from .errors import DeclarationError


@dataclasses.dataclass(frozen=True)
class KeyRules:
    """The parts of key=value syntax that differ between libraries."""

    assign: str = "="  # between key and value; the libraries strip spaces around it, so there are none
    separator: str = ","  # between items
    booleans: tuple[str, str] = ("true", "false")  # the literals of a boolean value
    nesting: bool = True  # whether a value may itself be a braced key list
    braced: bool = False  # whether every value is wrapped in braces, not only one that needs it
    edge_spaces: bool = True  # whether `{{ a }}` keeps the spaces at the ends of a value; else the library trims them

    def __post_init__(self) -> None:
        if not self.assign or not self.separator or self.assign == self.separator:
            raise DeclarationError(
                f"KeyRules(assign={self.assign!r}, separator={self.separator!r}): both are set and differ",
                code="TM-M036",
            )


KEYVAL: Final = KeyRules(nesting=False)  # the `keyval` package: a value is text
XKEYVAL: Final = KeyRules()  # `xkeyval`
PGFKEYS: Final = KeyRules()  # `pgfkeys`, also under TikZ and tcolorbox
KVOPTIONS: Final = KeyRules(nesting=False)  # `kvoptions` (declared options, on top of xkeyval)
L3KEYS: Final = KeyRules(edge_spaces=False)  # `l3keys`, with `\keys_set:nn`: trims a value however it is braced
