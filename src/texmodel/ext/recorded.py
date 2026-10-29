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


LENGTHS = list[Length]
"""A recorded list of lengths: `Recorded("Widths", kind=LENGTHS, fold=APPEND)`."""


@dataclasses.dataclass(frozen=True)
class Fold:
    """How each measurement joins the document's value: `update` is the TeX statement that sets register `$acc` from
    itself and `$x`, `identity` the value that changes nothing, `reduce` the same fold in Python. An `idempotent` fold
    may take the previous run's value into this run (a maximum cannot shrink mid-run); the others report that value
    alone, because a running total, or a list, is partial."""

    name: str
    update: Mapping[Any, str]
    identity: Mapping[Any, str]
    idempotent: bool
    reduce: Callable[[Iterable[float]], object]

    @property
    def kinds(self) -> tuple[Any, ...]:
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
APPEND = Fold(
    "append",
    {LENGTHS: r"\xdef$acc{\ifx$acc\@empty\else$acc,\fi\the\dimexpr$x\relax}"},
    {LENGTHS: ""},
    False,
    lambda xs: list(xs),
)

LIBRARY = r"""
    <<effective>>
    <<new_seen>>
    <<new_last>>
    \newcommand{\<<p>>@rec<<name>>refresh}{%
      <<refresh>>%
    }
    \newcommand{\<<p>>Record<<name>>}[1]{%
      <<update>>%
      \<<p>>@rec<<name>>refresh
    }
    \newcommand{\<<p>>@rec<<name>>read}[1]{%
      <<read_last>>%
      \<<p>>@rec<<name>>refresh
    }
    \AtEndDocument{%
      \if@filesw
        \immediate\write\@auxout{\string\providecommand\string\<<p>>@rec<<name>>read[1]{}}%
        \immediate\write\@auxout{\string\<<p>>@rec<<name>>read{<<seen_text>>}}%
      \fi
      <<unsettled>>%
    }
"""


def _warning(package: str, name: str) -> str:
    return (
        rf"\PackageWarningNoLine{{{package}}}{{{name} is not settled: this run used the last run's value.\MessageBreak "
        r"Rerun to set every card from the document's own}"
    )


class RecordedParts(NamedTuple):
    """What `Recorded.declare` registers: the command that records a measurement and the value that reads it."""

    record: type[Command]
    value: type[Value[Any]]


@dataclasses.dataclass(frozen=True)
class Recorded:
    """A document-wide value: `name` (CamelCase letters, the suffix of `\\<prefix>Record<Name>` and of the value
    `\\<prefix><Name>`), its `kind` (`Length`, `int`, or `LENGTHS`, a list of them) and the `fold` that combines
    measurements into it."""

    name: str
    kind: Any = Length
    fold: Fold = MAX

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name):
            raise DeclarationError(
                f"Recorded.name={self.name!r}: capital letter first, letters only", code="TM-M056", path="name"
            )
        if self.kind not in (Length, int, LENGTHS):
            raise DeclarationError(f"Recorded.kind={self.kind!r}: Length, int or LENGTHS", code="TM-M057", path="kind")
        if self.kind not in self.fold.kinds:
            raise DeclarationError(
                f"Recorded {self.name}: the {self.fold.name} fold does not take a {self.kind!r}",
                code="TM-M058",
                path="fold",
            )

    def declare(self, package: Package) -> RecordedParts:
        """The block of the package's `.sty`, the command `Record<Name>` (one argument, the measurement) and the value
        `<Name>`, which holds the fold so far: a length register, a macro that expands to the number for an `int`, or to
        the comma list for `LENGTHS`."""
        if not package.prefix:
            raise DeclarationError(
                f"Recorded {self.name}: the package has no prefix", code="TM-M059", path=package.name
            )
        acc, update = rf"\{package.prefix}{self.name}", self.fold.update[self.kind]
        seen = rf"\{package.prefix}@rec{self.name}seen"
        last = rf"\{package.prefix}@rec{self.name}last"
        identity = self.fold.identity[self.kind]
        fold = string.Template(update)
        warning = _warning(package.name, self.name)
        if self.kind is Length:  # a register: `\newlength` is what a `Value[Length]` is
            effective = rf"\newlength{{{acc}}}\global{acc}={identity}\relax"
            new = rf"\newlength{{$reg}}\global$reg={identity}\relax"
            refresh = rf"\global{acc}={last}\relax" + (fold.substitute(acc=acc, x=seen) if self.fold.idempotent else "")
            read_last, seen_text = rf"\global{last}=#1\relax", rf"\the{seen}"
            unsettled = rf"\ifdim{seen}={last}\else {warning}\fi"
        elif self.kind is int:  # a macro that expands to the number: what a `Value[Raw]` is, and usable as a number
            effective = rf"\newcommand{{{acc}}}{{{identity}}}"
            new = rf"\newcount{{$reg}}\global$reg={identity}\relax"
            scratch = r"\count@"
            refresh = rf"\global{scratch}={last}\relax" + (
                fold.substitute(acc=scratch, x=seen) if self.fold.idempotent else ""
            )
            refresh += rf"\xdef{acc}{{\the{scratch}}}"
            read_last, seen_text = rf"\global{last}=#1\relax", rf"\the{seen}"
            unsettled = rf"\ifnum{seen}={last}\else {warning}\fi"
        else:  # a comma list kept in a macro; strings are compared, because the `.aux` re-reads catcodes
            effective = rf"\newcommand{acc}{{}}"
            new = r"\newcommand$reg{}"
            refresh = rf"\xdef{acc}{{{last}}}"
            read_last, seen_text = rf"\gdef{last}{{#1}}", seen
            unsettled = rf"\csname str_if_eq:eeTF\endcsname{{{seen}}}{{{last}}}{{}}{{{warning}}}"
        lib = package.library(
            f"recorded-{self.name}",
            LIBRARY,
            fill={
                "effective": Raw(effective),
                "new_seen": Raw(string.Template(new).substitute(reg=seen)),
                "new_last": Raw(string.Template(new).substitute(reg=last)),
                "p": Raw(package.prefix),
                "name": Raw(self.name),
                "refresh": Raw(refresh),
                "update": Raw(fold.substitute(acc=seen, x="#1")),
                "read_last": Raw(read_last),
                "seen_text": Raw(seen_text),
                "unsettled": Raw(unsettled),
            },
        )
        length = self.kind is Length
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


def reduce(fold: Fold, values: Iterable[float]) -> object:
    """The fold of `values` in Python: what the TeX of the same fold must come to."""
    return fold.reduce(values)


__all__ = ["APPEND", "LENGTHS", "LIBRARY", "MAX", "MIN", "SUM", "Fold", "Recorded", "RecordedParts", "reduce"]
