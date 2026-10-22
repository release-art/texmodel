"""Body pieces (M8): what a component's `body` / `begin` / `end` may give, and how line ends are written.

A body is a string, a `TemplateRef` (a file next to the module), a `TexRaw` (a string with a whitespace policy), or a
sequence, iterator or generator of those. Each piece has its own `Whitespace`; one left as `None` takes the package's
default (`Package(whitespace=)`, itself `KEEP` unless told otherwise).

```python
def body(self):
    yield TexRaw(r'''
        \\par\\noindent
        {\\color{ac-ink}#text}
    ''', whitespace=Whitespace.TRIM)        # written as \\par\\noindent% / {\\color{ac-ink}#text}%
    yield r"\\par"                           # the package's default policy
```
"""

import dataclasses
import enum
import os
import textwrap
from collections.abc import Generator, Iterator, Sequence
from pathlib import Path

from .errors import DeclarationError


@enum.unique
class Whitespace(enum.Enum):
    """How the line ends of a body piece are written (M8). A newline in a macro body is a space token in TeX."""

    KEEP = "keep"  # as given: the author places any `%`
    TRIM = "trim"  # a `%` is added to each line, so line ends make no space; blank lines still end a paragraph


@dataclasses.dataclass(frozen=True)
class TexRaw:
    """TeX for a body, with `#name` holes: dedented and without leading or trailing blank lines. `whitespace` of `None`
    is the package's default."""

    body: str
    whitespace: Whitespace | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "body", textwrap.dedent(self.body).strip("\n"))


@dataclasses.dataclass(frozen=True, init=False)
class TemplateRef:
    """A body kept in a TeX file: `TemplateRef("fact.tex")`. Relative paths are relative to the module that defines the
    component, so the reference works wherever the package is installed; there is no lookup by name."""

    path: Path
    whitespace: Whitespace | None

    def __init__(self, path: str | os.PathLike[str], *, whitespace: Whitespace | None = None) -> None:
        object.__setattr__(self, "path", Path(path))
        object.__setattr__(self, "whitespace", whitespace)


type BodyPiece = TexRaw | str | TemplateRef
type BodyT = BodyPiece | Sequence[BodyPiece] | Iterator[BodyPiece] | Generator[BodyPiece]


def pieces_of(value: object) -> tuple[BodyPiece, ...] | None:
    """The pieces of what a body gave, or `None` if it is not a body."""
    if isinstance(value, TexRaw | str | TemplateRef):
        return (value,)
    if isinstance(value, Sequence | Iterator):
        found = tuple(value)  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
        if all(isinstance(p, TexRaw | str | TemplateRef) for p in found):  # pyright: ignore[reportUnknownVariableType]
            return found  # pyright: ignore[reportUnknownVariableType]
    return None


def _trim(line: str) -> str:
    line = line.rstrip()
    if not line or line.lstrip().startswith("%") or (line.endswith("%") and not line.endswith("\\%")):
        return line
    return f"{line}%"


def join(pieces: Sequence[TexRaw], default: Whitespace, owner: str) -> str:
    """The text of a body: pieces joined by newlines, each with its policy applied."""
    out: list[str] = []
    for piece in pieces:
        policy = piece.whitespace or default
        if policy is Whitespace.TRIM and "\\verb" in piece.body:
            raise DeclarationError(
                f"{owner}: a TRIM piece contains \\verb, whose line ends matter",
                code="TM-M025",
                hint="give that piece Whitespace.KEEP",
            )
        lines = piece.body.splitlines()
        out.extend(map(_trim, lines) if policy is Whitespace.TRIM else lines)
    return "\n".join(out)
