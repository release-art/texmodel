"""Writing a body as TeX: a constructive piece (`Cs`, `Group`, `Seq`, `Lit`, `Hole`, a `Ref`) as one line, and a body's
pieces joined line by line with their whitespace policy."""

from collections.abc import Callable, Sequence

from ..body import Comment, Cs, Group, Hole, Inline, Lit, Ref, Seq, Syntax, TexRaw, Whitespace
from ..errors import DeclarationError
from ..types import Raw, escape


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
