"""Typed preamble entries (§21, G3): each renders to one `Raw` and knows which `PreambleSlots` slots it may sit in.

```python
PreambleSlots(
    before_class=(RequireMetadata(lang="en-GB", pdfstandard="A-2b"),),
    before_package=(InputPath("res/"), PassOption("xcolor", "table"), InputIfExists("options")),
    after_package=(GraphicsPath("images/"), PdfInfo(title="Rex")),
)
```
"""

import dataclasses
import hashlib
import re
from collections.abc import Iterator, Mapping
from typing import ClassVar, Self

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


@dataclasses.dataclass(frozen=True)
class TrailerId:
    """The PDF trailer `/ID`, 16 bytes as 32 hex digits: `TrailerId("00112233445566778899AABBCCDDEEFF")`, or
    `TrailerId.of(seed)` for the first 16 bytes of the SHA-256 of `seed`. LuaTeX hashes the working directory into
    the ID otherwise, so the same source built in two directories differs (`TM-M089`)."""

    hex: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9A-Fa-f]{32}", self.hex):
            raise DeclarationError(
                f"TrailerId {self.hex!r}: give 32 hex digits", code="TM-M089", path="TrailerId", hint="16 bytes"
            )
        object.__setattr__(self, "hex", self.hex.upper())

    @classmethod
    def of(cls, seed: bytes) -> Self:
        return cls(hashlib.sha256(seed).hexdigest()[:32])

    def tex(self) -> str:
        return rf"\pdfvariable trailerid{{[<{self.hex}><{self.hex}>]}}"


_SAFE = re.compile(r"[A-Za-z0-9.,;:!?'()\[\]+*=/@|-]")
_INFO = {
    "title": "Title",
    "author": "Author",
    "subject": "Subject",
    "keywords": "Keywords",
    "producer": "Producer",
    "creator": "Creator",
}


def _xmp_text(text: str) -> str:
    r"""`text` as TeX that expands to exactly it, whatever it holds: runs of safe characters in `\detokenize`, every
    other character (TeX syntax, a space beside a space, non-ASCII) as `\char_generate:nn`. The XMP packet takes text,
    not the PDF string escapes of the Info dictionary, and escapes the XML itself."""
    out: list[str] = []
    run = ""
    for i, c in enumerate(text):
        if _SAFE.fullmatch(c) or (c == " " and 0 < i < len(text) - 1 and text[i - 1] != " " and text[i + 1] != " "):
            run += c
            continue
        out += [rf"\detokenize{{{run}}}"] if run else []
        out.append(rf"\csname char_generate:nn\endcsname{{{ord(c)}}}{{12}}")
        run = ""
    out += [rf"\detokenize{{{run}}}"] if run else []
    return "".join(out)


@dataclasses.dataclass(frozen=True, kw_only=True)
class PdfInfo:
    """What the PDF says about itself: `PdfInfo(title="Rex", producer="Acme Press", trailer_id=TrailerId(...))`. One
    declaration, three routes. `title`, `author`, `subject`, `keywords`, `producer` and `creator` go to the Info
    dictionary, PDF-escaped through `pdfmanagement_add:nnn` (§21), and to the XMP packet, through the document
    properties hyperref also uses, so they agree whether or not hyperref is loaded; `extra` is more Info entries
    (a key is letters only, `TM-M035`, and not one a field above has, `TM-M090`). `trailer_id` is
    `\\pdfvariable trailerid`, which wins over the one `Compiler(epoch=)` derives. The metadata routes need
    `\\DocumentMetadata`, so a document with them has a `RequireMetadata` in `before_class` (`TM-C009`)."""

    title: str | None = None
    author: str | None = None
    subject: str | None = None
    keywords: tuple[str, ...] = ()
    producer: str | None = None
    creator: str | None = None
    trailer_id: TrailerId | None = None
    extra: Mapping[str, str] = dataclasses.field(default_factory=dict[str, str])
    slots: ClassVar[tuple[str, ...]] = (BEFORE_PACKAGE, AFTER_PACKAGE)

    def __post_init__(self) -> None:
        if bad := [k for k in self.extra if not re.fullmatch(r"[A-Za-z]+", k)]:
            raise DeclarationError(f"PdfInfo key {bad[0]!r}: letters only", code="TM-M035", path="PdfInfo")
        if clash := [k for k in self.extra if k in _INFO.values()]:
            raise DeclarationError(
                f"PdfInfo extra key {clash[0]!r}: it has a field",
                code="TM-M090",
                path="PdfInfo",
                hint=f"use {clash[0].lower()}=",
            )

    def texts(self) -> dict[str, str]:
        """The fields that are set, by field name; the keywords as one string."""
        found = {name: getattr(self, name) for name in _INFO if name != "keywords"}
        found["keywords"] = ", ".join(self.keywords) if self.keywords else None
        return {name: text for name, text in found.items() if text is not None}

    @property
    def needs_metadata(self) -> bool:
        return bool(self.texts() or self.extra)

    def raw(self) -> Raw:
        def info(key: str, text: str) -> str:
            return f"\\csname pdfmanagement_add:nnn\\endcsname{{Info}}{{{key}}}{{(\\detokenize{{{pdf_escape(text)}}})}}"

        lines: list[str] = []
        for name, text in self.texts().items():
            lines += [info(_INFO[name], text), f"\\AddToDocumentProperties[hyperref]{{pdf{name}}}{{{_xmp_text(text)}}}"]
        lines += [info(key, text) for key, text in self.extra.items()]
        if self.trailer_id is not None:
            lines.append(self.trailer_id.tex())
        return Raw("\n".join(lines))


type Entry = PassOption | InputPath | InputIfExists | GraphicsPath | RequireMetadata | PdfInfo


@dataclasses.dataclass(frozen=True)
class PreambleSlots:
    """TeX a document places around its class and package lines (D3), each slot a tuple of `Raw` or a typed entry
    (`InputPath`, `GraphicsPath`, `PassOption`, `RequireMetadata`, `PdfInfo`; one in a slot it does not belong in is
    `TM-C008`).

    `before_class` is where `\\DocumentMetadata` must go; `before_package` is for what the package needs when it
    loads (`\\input@path`, package options); `after_package` is for what needs it loaded (`\\graphicspath`,
    per-document `\\renewcommand`s). Public names of the package used here must be declared (M8).
    """

    before_class: tuple[Raw | Entry, ...] = ()
    before_package: tuple[Raw | Entry, ...] = ()
    after_package: tuple[Raw | Entry, ...] = ()

    def items(self) -> Iterator[tuple[str, int, Raw | Entry]]:
        """Every item with its slot name and index, in document order: the path is `preamble.<slot>[<index>]`."""
        for slot, found in (
            ("before_class", self.before_class),
            ("before_package", self.before_package),
            ("after_package", self.after_package),
        ):
            for i, item in enumerate(found):
                yield slot, i, item


__all__ = [
    "Entry",
    "GraphicsPath",
    "InputIfExists",
    "InputPath",
    "PassOption",
    "PdfInfo",
    "PreambleSlots",
    "RequireMetadata",
    "TrailerId",
]
