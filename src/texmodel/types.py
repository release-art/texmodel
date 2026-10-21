"""Field types (T1): the closed vocabulary a component field may use.

`Text` is plain `str` to a type checker, so `Fact("A soft woof.")` type-checks, and a marker at runtime, so the renderer
and (later) the escaper know the field holds untrusted text that must be escaped on render (T3).
"""

from typing import Annotated, Final


class _TextMarker:
    def __repr__(self) -> str:
        return "Text"


TEXT: Final = _TextMarker()
Text = Annotated[str, TEXT]
