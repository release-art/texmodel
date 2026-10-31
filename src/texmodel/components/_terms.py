"""Grammar terms: how many of a component an environment allows."""

import dataclasses
from typing import TYPE_CHECKING, overload

from ..errors import DeclarationError

if TYPE_CHECKING:
    pass


@dataclasses.dataclass(frozen=True)
class Repeat:
    """How many of one component a grammar allows in a row (M4): `Fact.times(2, 3)`; a bare `Name` is exactly one."""

    kind: type
    lo: int
    hi: int | None

    def __str__(self) -> str:
        return f"{self.lo}-{'any' if self.hi is None else self.hi} {self.kind.__name__}"


@dataclasses.dataclass(frozen=True)
class Anywhere:
    """A grammar term (B3): zero or more `kind` between any two other terms and at both ends, in any number of
    places: `children = [Name, Anywhere(Heading), Fact.times(2, 3)]`. The kind may not also be an ordered term."""

    kind: type

    def __str__(self) -> str:
        return f"{self.kind.__name__} anywhere"


class Times:
    """`Fact.times(2, 3)`, `Fact.times(3)` (0 to 3), `Fact.times(2, None)` (2 or more), `.any()`, `.at_least_one()`."""

    def __init__(self, kind: type) -> None:
        self.kind = kind

    @overload
    def __call__(self, to: int | None, /) -> Repeat: ...
    @overload
    def __call__(self, from_: int, to: int | None, /) -> Repeat: ...
    def __call__(self, *bounds: int | None) -> Repeat:
        """`times(to)` allows 0 to `to`; `times(from_, to)` allows `from_` to `to`; `to=None` has no upper limit."""
        lo, hi = (0, bounds[0]) if len(bounds) == 1 else bounds if len(bounds) == 2 else (None, None)
        # `type(...) is int` also turns away floats and bools, which slip past the annotations at runtime.
        if type(lo) is not int or lo < 0 or not (hi is None or type(hi) is int and hi >= max(lo, 1)):
            raise DeclarationError(
                f"{self.kind.__name__}.times{bounds}: use (to) or (from, to), ints with 0 <= from <= to and 1 <= to; "
                "to=None means no limit",
                code="TM-M020",
                path=self.kind.__name__,
            )
        return Repeat(self.kind, lo, hi)

    def any(self) -> Repeat:
        """Zero or more."""
        return Repeat(self.kind, 0, None)

    def at_least_one(self) -> Repeat:
        """One or more."""
        return Repeat(self.kind, 1, None)
