r"""recorded: a value only the whole document knows (the widest label, the number of cards), carried between runs.

TeX reads the first card before it has seen the last, so a document-wide maximum is measured in one run, written to the
`.aux`, and used by the next: `latexmk` reruns until it stops moving. `Recorded` declares one, with the `fold` that
combines each card's measurement into it.

```python
label = Recorded("LabelWidth")                      # a length, the maximum
cards = Recorded("Cards", kind=int, fold=SUM)       # a count
record, width = label.declare(pkg)                  # `\apRecordLabelWidth{<length>}`, and the length `\apLabelWidth`
```

What it keeps right, each a failure that is silent if missed: the `.aux` is read inside a group, so the value is set
`\global`; a line the installed package does not know is swallowed (`\providecommand` first), as the `.aux` may come
from another version; and the run says when the value has not settled. Measure where a card names itself, at a fixed
size, and not inside a box LaTeX defers: a measurement that depends on the value never settles.
"""

import dataclasses
import math
import re
import string
import types
from collections.abc import Callable, Iterable, Mapping
from typing import Any, NamedTuple

from ..components import Command, Value
from ..errors import DeclarationError
from ..package import Package
from ..types import Length, Raw

_NAME = re.compile(r"[A-Z][A-Za-z]*")


@dataclasses.dataclass(frozen=True)
class Fold:
    """How each measurement joins the document's value: `update` is the TeX statement that sets register `$acc` from
    itself and `$x`, `identity` the value that changes nothing, `reduce` the same fold in Python. An `idempotent` fold
    may take the previous run's value into this run (a maximum cannot shrink mid-run); the others report that value
    alone, because a running total is partial."""

    name: str
    update: Mapping[type, str]
    identity: Mapping[type, str]
    idempotent: bool
    reduce: Callable[[Iterable[float]], float]

    @property
    def kinds(self) -> tuple[type, ...]:
        return tuple(self.update)


_MAX_INT = "2147483647"
MAX = Fold(
    "max",
    {Length: r"\ifdim$x>$acc\global$acc=$x\relax\fi", int: r"\ifnum$x>$acc\global$acc=$x\relax\fi"},
    {Length: "0pt", int: "0"},
    True,
    lambda xs: max(xs, default=0),
)
MIN = Fold(
    "min",
    {Length: r"\ifdim$x<$acc\global$acc=$x\relax\fi", int: r"\ifnum$x<$acc\global$acc=$x\relax\fi"},
    {Length: r"\maxdimen", int: _MAX_INT},
    True,
    lambda xs: min(xs, default=math.inf),
)
SUM = Fold(
    "sum",
    {Length: r"\global\advance$acc by $x\relax", int: r"\global\advance$acc by $x\relax"},
    {Length: "0pt", int: "0"},
    False,
    lambda xs: sum(xs),
)

LIBRARY = r"""
    <<effective>>
    \new<<kind>>{\<<p>>@rec<<name>>seen}
    \new<<kind>>{\<<p>>@rec<<name>>last}
    \global\<<p>>@rec<<name>>seen=<<identity>>\relax
    \global\<<p>>@rec<<name>>last=<<identity>>\relax
    \newcommand{\<<p>>@rec<<name>>refresh}{%
      <<refresh>>%
    }
    \newcommand{\<<p>>Record<<name>>}[1]{%
      <<update>>%
      \<<p>>@rec<<name>>refresh
    }
    \newcommand{\<<p>>@rec<<name>>read}[1]{%
      \global\<<p>>@rec<<name>>last=#1\relax
      \<<p>>@rec<<name>>refresh
    }
    \AtEndDocument{%
      \if@filesw
        \immediate\write\@auxout{\string\providecommand\string\<<p>>@rec<<name>>read[1]{}}%
        \immediate\write\@auxout{\string\<<p>>@rec<<name>>read{\the\<<p>>@rec<<name>>seen}}%
      \fi
      \if<<equal>>\else
        \PackageWarningNoLine{<<package>>}{<<name>> is not settled: this run used the last run's value.\MessageBreak
          Rerun to set every card from the document's own}%
      \fi
    }
"""


class RecordedParts(NamedTuple):
    """What `Recorded.declare` registers: the command that records a measurement and the value that reads it."""

    record: type[Command]
    value: type[Value[Any]]


@dataclasses.dataclass(frozen=True)
class Recorded:
    """A document-wide value: `name` (CamelCase letters, the suffix of `\\<prefix>Record<Name>` and of the value
    `\\<prefix><Name>`), its `kind` (`Length` or `int`) and the `fold` that combines measurements into it."""

    name: str
    kind: type = Length
    fold: Fold = MAX

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name):
            raise DeclarationError(
                f"Recorded.name={self.name!r}: capital letter first, letters only", code="TM-M056", path="name"
            )
        if self.kind not in (Length, int):
            raise DeclarationError(f"Recorded.kind={self.kind!r}: Length or int", code="TM-M057", path="kind")
        if self.kind not in self.fold.kinds:
            raise DeclarationError(
                f"Recorded {self.name}: the {self.fold.name} fold does not take a {self.kind.__name__}",
                code="TM-M058",
                path="fold",
            )

    def declare(self, package: Package) -> RecordedParts:
        """The block of the package's `.sty`, the command `Record<Name>` (one argument, the measurement) and the value
        `<Name>`, which holds the fold so far: a length register, or a count for an `int`."""
        if not package.prefix:
            raise DeclarationError(
                f"Recorded {self.name}: the package has no prefix", code="TM-M059", path=package.name
            )
        length = self.kind is Length
        acc, update = rf"\{package.prefix}{self.name}", self.fold.update[self.kind]
        seen = rf"\{package.prefix}@rec{self.name}seen"
        last = rf"\{package.prefix}@rec{self.name}last"
        fold = string.Template(update)
        if length:  # a register: `\newlength` is what a `Value[Length]` is
            effective = rf"\newlength{{{acc}}}\global{acc}={self.fold.identity[self.kind]}\relax"
            refresh = rf"\global{acc}={last}\relax" + (fold.substitute(acc=acc, x=seen) if self.fold.idempotent else "")
        else:  # a macro that expands to the number: what a `Value[Raw]` is, and usable wherever a number is
            effective = rf"\newcommand{{{acc}}}{{{self.fold.identity[self.kind]}}}"
            scratch = r"\count@"
            refresh = rf"\global{scratch}={last}\relax" + (
                fold.substitute(acc=scratch, x=seen) if self.fold.idempotent else ""
            )
            refresh += rf"\xdef{acc}{{\the{scratch}}}"
        lib = package.library(
            f"recorded-{self.name}",
            LIBRARY,
            fill={
                "kind": Raw("length" if length else "count"),
                "effective": Raw(effective),
                "p": Raw(package.prefix),
                "name": Raw(self.name),
                "package": Raw(package.name),
                "identity": Raw(self.fold.identity[self.kind]),
                "refresh": Raw(refresh),
                "update": Raw(fold.substitute(acc=seen, x="#1")),
                "equal": Raw(rf"{'dim' if length else 'num'}{seen}={last}"),
            },
        )
        record = types.new_class(
            f"Record{self.name}",
            (Command,),
            exec_body=lambda ns: ns.update(
                __doc__=f"Record a measurement of {self.name}.",
                __module__=package.name,
                __annotations__={"value": Raw},
                defined_by=lib,
            ),
        )
        value = types.new_class(
            self.name,
            (Value[Length if length else Raw],),
            exec_body=lambda ns: ns.update(
                __doc__=f"The {self.fold.name} of the {self.name} records, as of the last run.",
                __module__=package.name,
                defined_by=lib,
            ),
        )
        return RecordedParts(package.command(record), package.value(value))


def reduce(fold: Fold, values: Iterable[float]) -> float:
    """The fold of `values` in Python: what the TeX of the same fold must come to."""
    return fold.reduce(values)


__all__ = ["LIBRARY", "MAX", "MIN", "SUM", "Fold", "Recorded", "RecordedParts", "reduce"]
