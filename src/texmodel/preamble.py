"""Typed preamble entries (§21a 10, G3): each renders to one `Raw` and knows which `PreambleSlots` slots it may sit in.

```python
PreambleSlots(
    before_class=(RequireMetadata(lang="en-GB", pdfstandard="A-2b"),),
    before_package=(InputPath("res/"), PassOption("xcolor", "table"), InputIfExists("options")),
    after_package=(GraphicsPath("images/"), PdfInfo(Title="Rex")),
)
```
"""

import dataclasses
import re
from typing import ClassVar

from .errors import DeclarationError
from .types import Raw, pdf_escape

BEFORE_CLASS, BEFORE_PACKAGE, AFTER_PACKAGE = "before_class", "before_package", "after_package"


@dataclasses.dataclass(frozen=True)
class PassOption:
    """`\\PassOptionsToPackage{option}{package}`: before the package loads."""

    package: str
    option: str
    slots: ClassVar[tuple[str, ...]] = (BEFORE_CLASS, BEFORE_PACKAGE)

    def raw(self) -> Raw:
        return Raw(f"\\PassOptionsToPackage{{{self.option}}}{{{self.package}}}")


@dataclasses.dataclass(frozen=True, init=False)
class InputPath:
    """Where `\\input` and `\\usepackage` look: the package's own files must be found when it loads."""

    dirs: tuple[str, ...]
    slots: ClassVar[tuple[str, ...]] = (BEFORE_PACKAGE,)

    def __init__(self, *dirs: str) -> None:
        object.__setattr__(self, "dirs", dirs)

    def raw(self) -> Raw:
        return Raw(f"\\makeatletter\\def\\input@path{{{''.join(f'{{{d}}}' for d in self.dirs)}}}\\makeatother")


@dataclasses.dataclass(frozen=True)
class InputIfExists:
    """`\\InputIfFileExists{name}{}{}`: reads `name.tex` when the file is there and does nothing otherwise. A name is
    letters, digits and `. _ / -` (`TM-M044`)."""

    name: str
    slots: ClassVar[tuple[str, ...]] = (BEFORE_PACKAGE, AFTER_PACKAGE)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", self.name):
            raise DeclarationError(
                f"InputIfExists name {self.name!r}: letters, digits and . _ / - only",
                code="TM-M044",
                path="InputIfExists",
            )

    def raw(self) -> Raw:
        return Raw(f"\\InputIfFileExists{{{self.name}}}{{}}{{}}")


@dataclasses.dataclass(frozen=True, init=False)
class GraphicsPath:
    """`\\graphicspath`: it needs graphicx, which the package loads. The current directory is the empty first group."""

    dirs: tuple[str, ...]
    include_cwd: bool
    slots: ClassVar[tuple[str, ...]] = (AFTER_PACKAGE,)

    def __init__(self, *dirs: str, include_cwd: bool = True) -> None:
        object.__setattr__(self, "dirs", dirs)
        object.__setattr__(self, "include_cwd", include_cwd)

    def raw(self) -> Raw:
        groups = ("{}" if self.include_cwd else "") + "".join(f"{{{d}}}" for d in self.dirs)
        return Raw(f"\\graphicspath{{{groups}}}")


@dataclasses.dataclass(frozen=True, init=False)
class RequireMetadata:
    """`\\DocumentMetadata{key=value, ...}`: before `\\documentclass`. A value with `,` `=` or a space is braced."""

    entries: tuple[tuple[str, str], ...]
    slots: ClassVar[tuple[str, ...]] = (BEFORE_CLASS,)

    def __init__(self, **entries: str) -> None:
        object.__setattr__(self, "entries", tuple(entries.items()))

    def raw(self) -> Raw:
        def value(v: str) -> str:
            return f"{{{v}}}" if any(c in v for c in ",= ") else v

        return Raw(f"\\DocumentMetadata{{{', '.join(f'{k}={value(v)}' for k, v in self.entries)}}}")


@dataclasses.dataclass(frozen=True, init=False)
class PdfInfo:
    """`PdfInfo(Title="Rex")`: entries of the PDF Info dictionary. Each value is PDF-escaped and written through
    `pdfmanagement_add:nnn`, so any text reaches the PDF as it is (§21a 9); the route needs `\\DocumentMetadata`, so a
    document with one has a `RequireMetadata` in `before_class` (`TM-C009`). A key is letters only (`TM-M035`)."""

    entries: tuple[tuple[str, str], ...]
    slots: ClassVar[tuple[str, ...]] = (BEFORE_PACKAGE, AFTER_PACKAGE)

    def __init__(self, **entries: str) -> None:
        if bad := [k for k in entries if not re.fullmatch(r"[A-Za-z]+", k)]:
            raise DeclarationError(f"PdfInfo key {bad[0]!r}: letters only", code="TM-M035", path="PdfInfo")
        object.__setattr__(self, "entries", tuple(entries.items()))

    def raw(self) -> Raw:
        return Raw(
            "\n".join(
                f"\\csname pdfmanagement_add:nnn\\endcsname{{Info}}{{{k}}}{{(\\detokenize{{{pdf_escape(v)}}})}}"
                for k, v in self.entries
            )
        )


type Entry = PassOption | InputPath | InputIfExists | GraphicsPath | RequireMetadata | PdfInfo


__all__ = ["Entry", "GraphicsPath", "InputIfExists", "InputPath", "PassOption", "PdfInfo", "RequireMetadata"]
