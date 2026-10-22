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
import re
import textwrap
from collections.abc import Callable, Generator, Iterator, Sequence
from pathlib import Path
from typing import ClassVar, dataclass_transform

from .errors import DeclarationError, Violation


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


@dataclasses.dataclass(frozen=True)
class Hole:
    """The argument `name` of the component whose body this is, as `#name` (M8)."""

    name: str


@enum.unique
class RefKind(enum.Enum):
    CALL = "call"  # a command: `\\acFact{...}`
    OPEN = "open"  # an environment's start: `\\begin{acBox}{...}`
    CLOSE = "close"  # an environment's end: `\\end{acBox}`


@dataclasses.dataclass(frozen=True)
class Ref:
    """A body piece that calls a declared component: `Fact.call(Hole("text"))`. `values` has one entry per argument of
    `target`, in declared order (`None` for an optional one left out). Built by `call`, `open` and `close` on the
    component class, which check the arguments; it is written with the target's prefix, and a target of another package
    makes that package a requirement of this one (§21a 17)."""

    target: type
    kind: RefKind
    values: tuple[object, ...]
    whitespace: Whitespace | None = None  # `None` is the package's default

    def with_whitespace(self, whitespace: Whitespace) -> "Ref":
        return dataclasses.replace(self, whitespace=whitespace)


_COMMENT_HOLE = re.compile(r"##|#(?P<name>[A-Za-z_]\w*)")


@dataclass_transform(frozen_default=True)
class Comment:
    """A comment (§21a 21): every line it renders starts with `% `, so no value can leave it, and nothing is escaped.
    `Comment("note")` is a text; a subclass declares fields and a `template` with `#name` holes (`##` is a `#`):

    ```python
    class CardHeader(Comment):
        '''The audit block above a card.'''
        template = "Card: #name"
        name: str
    ```

    As a body piece it renders its lines in place; as a child of an environment or a top-level node of a document it is
    transparent to the grammar. It claims no control sequence, so no package registers it. A hole that is not a field,
    or a field the template never uses, is refused when the class is defined (`TM-M028`)."""

    template: ClassVar[str] = "#text"
    __tm_fields__: ClassVar[tuple[str, ...]] = ("text",)
    text: str

    def __init__(self, text: str) -> None:
        object.__setattr__(self, "text", textwrap.dedent(text).strip("\n"))

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "template" not in cls.__dict__:
            raise DeclarationError(f"{cls.__qualname__}: no template", code="TM-M028", path=cls.__name__)
        cls.template = textwrap.dedent(cls.template).strip("\n")
        dataclasses.dataclass(frozen=True)(cls)
        cls.__tm_fields__ = tuple(f.name for f in dataclasses.fields(cls))  # pyright: ignore[reportArgumentType]
        holes = {m["name"] for m in _COMMENT_HOLE.finditer(cls.template) if m["name"]}
        if wrong := sorted(holes ^ set(cls.__tm_fields__)):
            raise DeclarationError(
                f"{cls.__qualname__}: holes and fields differ: {wrong} (a hole must be a field, a field must be used)",
                code="TM-M028",
                path=cls.__name__,
                hint="use #name for each field, ## for a literal #",
            )

    def __setattr__(self, name: str, value: object) -> None:
        raise dataclasses.FrozenInstanceError(name)

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and other.text == self.text  # pyright: ignore[reportAttributeAccessIssue]

    def __hash__(self) -> int:
        return hash((type(self), self.text))

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.text!r})"

    def validate(self) -> list[Violation]:
        """A comment breaks no rule."""
        return []

    def lines(self) -> tuple[str, ...]:
        """The comment, one `% ` line per line of the filled template (a blank line is `%`)."""
        filled = _COMMENT_HOLE.sub(lambda m: "#" if m[0] == "##" else getattr(self, m["name"]), self.template)
        return tuple(f"% {line}".rstrip() for line in filled.strip("\n").splitlines())

    def render(self) -> str:
        return "\n".join(self.lines())


type BodyPiece = TexRaw | str | TemplateRef | Ref | Comment
type BodyT = BodyPiece | Sequence[BodyPiece] | Iterator[BodyPiece] | Generator[BodyPiece]


def pieces_of(value: object) -> tuple[BodyPiece, ...] | None:
    """The pieces of what a body gave, or `None` if it is not a body."""
    if isinstance(value, TexRaw | str | TemplateRef | Ref | Comment):
        return (value,)
    if isinstance(value, Sequence | Iterator):
        found = tuple(value)  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
        if all(isinstance(p, TexRaw | str | TemplateRef | Ref | Comment) for p in found):  # pyright: ignore[reportUnknownVariableType]
            return found  # pyright: ignore[reportUnknownVariableType]
    return None


def _trim(line: str) -> str:
    line = line.rstrip()
    if not line or line.lstrip().startswith("%") or (line.endswith("%") and not line.endswith("\\%")):
        return line
    return f"{line}%"


def join(
    pieces: Sequence[TexRaw | Ref | Comment], default: Whitespace, owner: str, ref_text: Callable[[Ref], str]
) -> str:
    """The text of a body: pieces joined by newlines, each with its policy applied; `ref_text` writes a `Ref`."""
    out: list[str] = []
    for piece in pieces:
        if isinstance(piece, Comment):
            out.extend(piece.lines())
            continue
        policy = piece.whitespace or default
        if isinstance(piece, Ref):
            out.append(_trim(ref_text(piece)) if policy is Whitespace.TRIM else ref_text(piece))
            continue
        if policy is Whitespace.TRIM and "\\verb" in piece.body:
            raise DeclarationError(
                f"{owner}: a TRIM piece contains \\verb, whose line ends matter",
                code="TM-M025",
                hint="give that piece Whitespace.KEEP",
            )
        lines = piece.body.splitlines()
        out.extend(map(_trim, lines) if policy is Whitespace.TRIM else lines)
    return "\n".join(out)
