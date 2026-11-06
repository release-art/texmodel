r"""enumitem: List layout.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

import dataclasses

from texmodel.components import Command
from texmodel.errors import ValueRuleError
from texmodel.interface import Flag, Item
from texmodel.keys import KEYVAL
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import AsTeX, Length, Name, Raw

package = Package("enumitem", prefix="", adopted=True)


@dataclasses.dataclass(frozen=True)
class Lists(AsTeX):
    """Which lists a `SetList` changes: kinds and nesting levels, `Lists((Name("itemize"),), (1, 2))` is `itemize,1,2`.
    A level is 1 to 6 (`TM-C046`)."""

    kinds: tuple[Name, ...] = ()
    levels: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not (self.kinds or self.levels) or not all(1 <= n <= 6 for n in self.levels):
            raise ValueRuleError(
                "Lists: give a list kind or a level from 1 to 6", code="TM-C046", hint='Lists((Name("itemize"),), (1,))'
            )

    def render(self) -> str:
        return ",".join([*(k.tex for k in self.kinds), *map(str, self.levels)])


class ListOptions(KeyVals, rules=KEYVAL):
    r"""The keys of `\setlist`: `ListOptions(noitemsep=True, leftmargin=Length("1em"))`; `label` is TeX
    (`\alph*`); `extra` takes the rest."""

    noitemsep: Flag = False
    nosep: Flag = False
    leftmargin: Length | None = None
    itemsep: Length | None = None
    topsep: Length | None = None
    parsep: Length | None = None
    partopsep: Length | None = None
    labelsep: Length | None = None
    label: Raw | None = None
    start: int | None = None
    resume: Flag = False
    extra: Item[Raw] | None = None


@package.command
class SetList(Command):
    r"""Change list settings: `\setlist[itemize]{noitemsep}`."""

    cs = "setlist"
    options: ListOptions
    lists: Lists | None = None
