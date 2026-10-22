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
from .types import Raw, escape


@enum.unique
class Whitespace(enum.Enum):
    """How the line ends of a body piece are written (M8). A newline in a macro body is a space token in TeX."""

    KEEP = "keep"  # as given: the author places any `%`
    TRIM = "trim"  # a `%` is added to each line, so line ends make no space; blank lines still end a paragraph


@enum.unique
class Syntax(enum.Enum):
    """The category codes TeX reads a body with (§21a 12). A body has one syntax; the `.sty` switches on `EXPL3` around
    the definition (`\\ExplSyntaxOn` / `\\ExplSyntaxOff`), where a space is ignored and `~` is the space."""

    LATEX2E = "latex2e"
    EXPL3 = "expl3"


@dataclasses.dataclass(frozen=True)
class TexRaw:
    """TeX for a body, with `#name` holes: dedented and without leading or trailing blank lines. `whitespace` of `None`
    is the package's default; it is ignored in `Syntax.EXPL3`, where line ends make no space."""

    body: str
    whitespace: Whitespace | None = None
    syntax: Syntax = Syntax.LATEX2E

    def __post_init__(self) -> None:
        object.__setattr__(self, "body", textwrap.dedent(self.body).strip("\n"))


@dataclasses.dataclass(frozen=True, init=False)
class TemplateRef:
    """A body kept in a TeX file: `TemplateRef("fact.tex")`. Relative paths are relative to the module that defines the
    component, so the reference works wherever the package is installed; there is no lookup by name."""

    path: Path
    whitespace: Whitespace | None
    syntax: Syntax

    def __init__(
        self, path: str | os.PathLike[str], *, whitespace: Whitespace | None = None, syntax: Syntax = Syntax.LATEX2E
    ) -> None:
        object.__setattr__(self, "path", Path(path))
        object.__setattr__(self, "whitespace", whitespace)
        object.__setattr__(self, "syntax", syntax)


def template_text(ref: TemplateRef, module_file: str, owner: str) -> str:
    """The text of a template file; a relative path is relative to the module at `module_file` (`TM-M005`)."""
    path = ref.path if ref.path.is_absolute() else Path(module_file).parent / ref.path
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DeclarationError(f"{owner}: cannot read {path}: {exc.strerror}", code="TM-M005", path=owner) from exc


@dataclasses.dataclass(frozen=True)
class Library:
    """A block of TeX the `.sty` carries as it is (§21a 12), made by `Package.library`: `text` is dedented and has no
    blank edges, and nothing is added or rewritten (`#1` stays `#1`). `owner` is the package that made it."""

    name: str
    text: str
    syntax: Syntax
    origin: str  # "inline" or the template's file name, for the provenance comment
    owner: object = dataclasses.field(compare=False, repr=False)


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


HOLE = re.compile(r"##|#(?P<name>[A-Za-z_]\w*)")  # `##` is a literal `#`


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
        if "type" in cls.__tm_fields__:
            raise DeclarationError(
                f"{cls.__qualname__}.type: `type` names the component in data, so it cannot be a field",
                code="TM-M030",
                path=f"{cls.__name__}.type",
                hint="call the field something else, e.g. `kind`",
            )
        holes = {m["name"] for m in HOLE.finditer(cls.template) if m["name"]}
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
        filled = HOLE.sub(lambda m: "#" if m[0] == "##" else getattr(self, m["name"]), self.template)
        return tuple(f"% {line}".rstrip() for line in filled.strip("\n").splitlines())

    def render(self) -> str:
        return "\n".join(self.lines())


_CONTROL_WORDS = {Syntax.LATEX2E: re.compile(r"[A-Za-z@]+"), Syntax.EXPL3: re.compile(r"[A-Za-z@_:]+")}


@dataclasses.dataclass(frozen=True)
class Cs:
    """A control sequence, `Cs("par")` is `\\par`: the name is letters and `@` only, and in `Syntax.EXPL3` also `_` and
    `:` (`TM-M027`)."""

    name: str
    syntax: Syntax = Syntax.LATEX2E

    def __post_init__(self) -> None:
        if not _CONTROL_WORDS[self.syntax].fullmatch(self.name):
            raise DeclarationError(
                f"Cs({self.name!r}): a {self.syntax.value} control word has "
                + ("letters, @, _ and : only" if self.syntax is Syntax.EXPL3 else "letters and @ only"),
                code="TM-M027",
                hint="write the name without the backslash, e.g. Cs('par')",
            )


@dataclasses.dataclass(frozen=True)
class Lit:
    """Text, escaped as a `Text` field is (T3): `Lit("50% & #1")` is `50\\% \\& \\#1`.
    In `Syntax.EXPL3` a space is `~`."""

    text: str


@dataclasses.dataclass(frozen=True, init=False)
class Group:
    """`{...}` around its pieces: balanced by construction. A piece is a `Group`, `Seq`, `Cs`, `Lit`, `Hole`, `Ref` or
    a `Raw` (whose braces are already checked)."""

    pieces: tuple["Inline", ...]

    def __init__(self, *pieces: "Inline") -> None:
        object.__setattr__(self, "pieces", pieces)


@dataclasses.dataclass(frozen=True, init=False)
class Seq:
    """Pieces one after another with no braces: `Seq(Cs("textbf"), Group(Hole("text")))` is `\\textbf{#text}`."""

    pieces: tuple["Inline", ...]

    def __init__(self, *pieces: "Inline") -> None:
        object.__setattr__(self, "pieces", pieces)


type Inline = Group | Seq | Cs | Lit | Hole | Ref | Raw
type BodyPiece = TexRaw | str | TemplateRef | Ref | Comment | Group | Seq | Cs | Lit | Hole
type BodyT = BodyPiece | Sequence[BodyPiece] | Iterator[BodyPiece] | Generator[BodyPiece]


_PIECES = (TexRaw, str, TemplateRef, Ref, Comment, Group, Seq, Cs, Lit, Hole)


def refs_in(piece: object) -> Iterator[Ref]:
    """Every `Ref` in a piece, nested ones included: they are what a body depends on."""
    if isinstance(piece, Ref):
        yield piece
        for value in piece.values:  # a call inside an argument
            yield from refs_in(value)
    elif isinstance(piece, Group | Seq):
        for inner in piece.pieces:
            yield from refs_in(inner)


def syntaxes_in(piece: object) -> Iterator[Syntax]:
    """The syntax every `TexRaw` and `Cs` in a piece names, nested ones included; other pieces have none."""
    if isinstance(piece, TexRaw | Cs):
        yield piece.syntax
    elif isinstance(piece, Group | Seq):
        for inner in piece.pieces:
            yield from syntaxes_in(inner)


def text_of(text: str, syntax: Syntax) -> str:
    """`Lit` and argument text as the syntax reads it: expl3 ignores a space, so it is written `~`."""
    return escape(text).replace(" ", "~") if syntax is Syntax.EXPL3 else escape(text)


def _loose_start(piece: Inline) -> bool:
    """Can the text begin with a letter (a `Lit`, `Raw` or hole value), which a preceding control word would absorb?"""
    if isinstance(piece, Seq):
        return bool(piece.pieces) and _loose_start(piece.pieces[0])
    return isinstance(piece, Lit | Raw | Hole)


def _ends_with_cs(piece: Inline) -> bool:
    if isinstance(piece, Seq):
        return bool(piece.pieces) and _ends_with_cs(piece.pieces[-1])
    return isinstance(piece, Cs)


def inline_text(piece: Inline, ref_text: Callable[[Ref], str], syntax: Syntax = Syntax.LATEX2E) -> str:
    """The TeX of a constructive piece. A space follows a control word when the next text could continue its name."""
    if isinstance(piece, Lit):
        return text_of(piece.text, syntax)
    if isinstance(piece, Raw):
        return piece.tex
    if isinstance(piece, Hole):
        return f"#{piece.name}"
    if isinstance(piece, Ref):
        return ref_text(piece)
    if isinstance(piece, Cs):
        return f"\\{piece.name}"
    out: list[str] = []
    for i, inner in enumerate(piece.pieces):
        out.append(inline_text(inner, ref_text, syntax))
        if i + 1 < len(piece.pieces) and _ends_with_cs(inner) and _loose_start(piece.pieces[i + 1]):
            out.append(" ")
    text = "".join(out)
    return f"{{{text}}}" if isinstance(piece, Group) else text


def pieces_of(value: object) -> tuple[BodyPiece, ...] | None:
    """The pieces of what a body gave, or `None` if it is not a body."""
    if isinstance(value, _PIECES):
        return (value,)
    if isinstance(value, Sequence | Iterator):
        found = tuple(value)  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
        if all(isinstance(p, _PIECES) for p in found):  # pyright: ignore[reportUnknownVariableType]
            return found  # pyright: ignore[reportUnknownVariableType]
    return None


def _trim(line: str) -> str:
    line = line.rstrip()
    if not line or line.lstrip().startswith("%") or (line.endswith("%") and not line.endswith("\\%")):
        return line
    return f"{line}%"


def join(
    pieces: Sequence[TexRaw | Ref | Comment | Group | Seq | Cs | Lit | Hole],
    default: Whitespace,
    owner: str,
    ref_text: Callable[[Ref], str],
    syntax: Syntax = Syntax.LATEX2E,
) -> str:
    """The text of a body: pieces joined by newlines, each with its policy applied (none in `Syntax.EXPL3`, whose line
    ends make no space); `ref_text` writes a `Ref`."""
    out: list[str] = []
    expl3 = syntax is Syntax.EXPL3
    for piece in pieces:
        if isinstance(piece, Comment):
            out.extend(piece.lines())
            continue
        if not isinstance(piece, TexRaw):  # a Ref or a constructive piece is one line, in the package's policy
            policy = Whitespace.KEEP if expl3 else (piece.whitespace if isinstance(piece, Ref) else None) or default
            text = inline_text(piece, ref_text, syntax)
            out.append(_trim(text) if policy is Whitespace.TRIM else text)
            continue
        policy = Whitespace.KEEP if expl3 else piece.whitespace or default
        if policy is Whitespace.TRIM and "\\verb" in piece.body:
            raise DeclarationError(
                f"{owner}: a TRIM piece contains \\verb, whose line ends matter",
                code="TM-M025",
                hint="give that piece Whitespace.KEEP",
            )
        lines = piece.body.splitlines()
        out.extend(map(_trim, lines) if policy is Whitespace.TRIM else lines)
    return "\n".join(out)
