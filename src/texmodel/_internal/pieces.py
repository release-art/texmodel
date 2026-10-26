"""Reading what a component's body gave (`texmodel.body`): its pieces, what they refer to, the syntax they name, and the
file a template is in."""

from collections.abc import Iterator, Sequence
from pathlib import Path

from ..body import BodyPiece, Comment, Cs, Group, Hole, Lit, Ref, Seq, Syntax, TemplateRef, TexRaw
from ..errors import DeclarationError

_PIECES = (TexRaw, str, TemplateRef, Ref, Comment, Group, Seq, Cs, Lit, Hole)


def template_text(ref: TemplateRef, module_file: str, owner: str) -> str:
    """The text of a template file; a relative path is relative to the module at `module_file` (`TM-M005`)."""
    path = ref.path if ref.path.is_absolute() else Path(module_file).parent / ref.path
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DeclarationError(f"{owner}: cannot read {path}: {exc.strerror}", code="TM-M005", path=owner) from exc


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


def pieces_of(value: object) -> tuple[BodyPiece, ...] | None:
    """The pieces of what a body gave, or `None` if it is not a body."""
    if isinstance(value, _PIECES):
        return (value,)
    if isinstance(value, Sequence | Iterator):
        found = tuple(value)  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
        if all(isinstance(p, _PIECES) for p in found):  # pyright: ignore[reportUnknownVariableType]
            return found  # pyright: ignore[reportUnknownVariableType]
    return None
