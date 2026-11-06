"""Typed preamble entries (§21, G3): each renders to one `Raw` and knows which `PreambleSlots` slots it may sit in.
`RequireMetadata` and `PdfInfo` are not slot entries: a `Document` takes them as `metadata=` and `pdf=`, and the plan
places them.

```python
PreambleSlots(
    before_package=(InputPath("res/"), PassOption("xcolor", "table"), InputIfExists("options")),
    after_package=(GraphicsPath("images/"),),
)
```
"""

import dataclasses
import datetime
import enum
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


@enum.unique
class MetadataPolicy(enum.Enum):
    r"""What a document class does with `\\DocumentMetadata` (`Package(metadata=...)`): `ALLOWED` takes it, `REQUIRED`
    needs it (the plan writes an empty one when the document has none), `REFUSED` stops the plan (`beamer`)."""

    ALLOWED = "allowed"
    REQUIRED = "required"
    REFUSED = "refused"


_UNSAFE_VALUE = re.compile(r"[{}%\\#]")


@dataclasses.dataclass(frozen=True, kw_only=True)
class RequireMetadata:
    r"""`\DocumentMetadata{...}`, before `\documentclass`: `RequireMetadata(lang="en-GB", pdfstandard=("A-2b",))`.
    `colorprofiles` maps an intent's subtype to its profile file, `extra` is any other key (`tagging`, `xmp`; letters,
    digits, `-` and `/`, not one a field has: `TM-M091`, `TM-M092`). A value has no `{ } % \ #` (`TM-M093`). Set as
    `Document(metadata=...)`; a document with a `PdfInfo` gets an empty one when it has none."""

    lang: str | None = None
    pdfversion: str | None = None
    pdfstandard: tuple[str, ...] = ()
    colorprofiles: Mapping[str, str] = dataclasses.field(default_factory=dict[str, str])
    extra: Mapping[str, str] = dataclasses.field(default_factory=dict[str, str])

    def __post_init__(self) -> None:
        if bad := [k for k in self.extra if not re.fullmatch(r"[A-Za-z][A-Za-z0-9/-]*", k)]:
            raise DeclarationError(f"RequireMetadata key {bad[0]!r}: letters, digits, - and /", code="TM-M091")
        if clash := [k for k in self.extra if k in _METADATA_FIELDS]:
            raise DeclarationError(
                f"RequireMetadata extra key {clash[0]!r}: it has a field", code="TM-M092", hint=f"use {clash[0]}="
            )
        texts = [*self.pdfstandard, *self.colorprofiles, *self.colorprofiles.values(), *self.extra.values()]
        texts += [t for t in (self.lang, self.pdfversion) if t is not None]
        if bad := [t for t in texts if _UNSAFE_VALUE.search(t)]:
            raise DeclarationError(
                f"RequireMetadata value {bad[0]!r}: TeX reads `{{ }} % \\ #` as syntax", code="TM-M093"
            )

    def entries(self) -> dict[str, str]:
        """The keys that are set, in the order they are written."""
        found = {
            "lang": self.lang,
            "pdfstandard": ",".join(self.pdfstandard) or None,
            "pdfversion": self.pdfversion,
            "colorprofiles": ",".join(f"{k}={v}" for k, v in self.colorprofiles.items()) or None,
        }
        return {k: v for k, v in found.items() if v is not None} | dict(self.extra)

    def raw(self) -> Raw:
        def value(v: str) -> str:
            return f"{{{v}}}" if any(c in v for c in ",= ") else v

        return Raw(f"\\DocumentMetadata{{{', '.join(f'{k}={value(v)}' for k, v in self.entries().items())}}}")


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


_METADATA_FIELDS = ("lang", "pdfversion", "pdfstandard", "colorprofiles")
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
    r"""What the PDF says about itself: `PdfInfo(title="Rex", producer="Acme Press", trailer_id=TrailerId(...))`, set
    as `Document(pdf=...)`. One declaration, three routes. `title`, `author`, `subject`, `keywords`, `producer` and
    `creator` go to the Info dictionary, PDF-escaped through `pdfmanagement_add:nnn` (§21), and to the XMP packet,
    through the document properties hyperref also uses, so they agree whether or not hyperref is loaded. `created` and
    `modified` (with a time zone, stored as UTC: `TM-M094`) are `CreationDate` and `ModDate` in both. `extra` is more
    Info entries (a key is letters only, `TM-M035`, and not one a field has, `TM-M090`). `trailer_id` is
    `\pdfvariable trailerid`, which wins over the one `Compiler(epoch=)` derives. The metadata routes need
    `\DocumentMetadata`, which the plan writes empty when the document has no `metadata`."""

    title: str | None = None
    author: str | None = None
    subject: str | None = None
    keywords: tuple[str, ...] = ()
    producer: str | None = None
    creator: str | None = None
    created: datetime.datetime | None = None
    modified: datetime.datetime | None = None
    trailer_id: TrailerId | None = None
    extra: Mapping[str, str] = dataclasses.field(default_factory=dict[str, str])

    def __post_init__(self) -> None:
        if bad := [k for k in self.extra if not re.fullmatch(r"[A-Za-z]+", k)]:
            raise DeclarationError(f"PdfInfo key {bad[0]!r}: letters only", code="TM-M035", path="PdfInfo")
        if clash := [k for k in self.extra if k in (*_INFO.values(), "CreationDate", "ModDate")]:
            raise DeclarationError(
                f"PdfInfo extra key {clash[0]!r}: it has a field",
                code="TM-M090",
                path="PdfInfo",
                hint=f"use {clash[0].lower()}=",
            )
        if naive := [n for n in ("created", "modified") if (d := getattr(self, n)) is not None and d.tzinfo is None]:
            raise DeclarationError(
                f"PdfInfo {naive[0]}: give a time zone",
                code="TM-M094",
                path="PdfInfo",
                hint="datetime(..., tzinfo=UTC); the PDF stores UTC",
            )

    def texts(self) -> dict[str, str]:
        """The fields that are set, by field name; the keywords as one string."""
        found = {name: getattr(self, name) for name in _INFO if name != "keywords"}
        found["keywords"] = ", ".join(self.keywords) if self.keywords else None
        return {name: text for name, text in found.items() if text is not None}

    @property
    def needs_metadata(self) -> bool:
        return bool(self.texts() or self.extra or self.created or self.modified)

    def raw(self) -> Raw:
        def info(key: str, text: str) -> str:
            return f"\\csname pdfmanagement_add:nnn\\endcsname{{Info}}{{{key}}}{{(\\detokenize{{{pdf_escape(text)}}})}}"

        lines: list[str] = []
        for name, text in self.texts().items():
            lines += [info(_INFO[name], text), f"\\AddToDocumentProperties[hyperref]{{pdf{name}}}{{{_xmp_text(text)}}}"]
        lines += [info(key, text) for key, text in self.extra.items()]
        for name, moment in (("creationdate", self.created), ("moddate", self.modified)):
            if moment is not None:
                stamp = moment.astimezone(datetime.UTC).strftime("D:%Y%m%d%H%M%SZ")
                lines.append(f"\\AddToDocumentProperties[document]{{{name}}}{{{stamp}}}")
        if self.trailer_id is not None:
            lines.append(self.trailer_id.tex())
        return Raw("\n".join(lines))


type Entry = PassOption | InputPath | InputIfExists | GraphicsPath


@dataclasses.dataclass(frozen=True)
class PreambleSlots:
    """TeX a document places around its class and package lines (D3), each slot a tuple of `Raw` or a typed entry
    (`InputPath`, `GraphicsPath`, `PassOption`, `InputIfExists`; one in a slot it does not belong in is `TM-C008`).

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
    "MetadataPolicy",
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
