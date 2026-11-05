"""Preamble slots as data (`spec`): each entry is a model that names its entry with `"type"`; building the entry is
the check, so what an entry refuses is a data error too."""

import abc
import dataclasses
import datetime
from typing import Annotated, Literal

import pydantic

from ..errors import DeclarationError
from ..preamble import (
    Entry,
    GraphicsPath,
    InputIfExists,
    InputPath,
    PassOption,
    PdfInfo,
    PreambleSlots,
    RequireMetadata,
    TrailerId,
)
from ..types import Raw


class Built(pydantic.BaseModel):
    """Data that builds a value: building it is the check, so what the value refuses is a data error too."""

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    @abc.abstractmethod
    def build(self) -> object: ...

    @pydantic.model_validator(mode="after")
    def _constructible(self) -> "Built":
        try:
            self.build()
        except DeclarationError as exc:
            raise ValueError(str(exc)) from exc
        return self


class EntryModel(Built):
    """An entry as data: `{"type": "PassOption", "package": ..., "option": ...}` (§21)."""

    @abc.abstractmethod
    def entry(self) -> Entry: ...

    def build(self) -> object:
        return self.entry()


class PassOptionEntry(EntryModel):
    type: Literal["PassOption"]
    package: str
    option: str

    def entry(self) -> Entry:
        return PassOption(self.package, self.option)


class InputPathEntry(EntryModel):
    type: Literal["InputPath"]
    dirs: tuple[str, ...]

    def entry(self) -> Entry:
        return InputPath(*self.dirs)


class InputIfExistsEntry(EntryModel):
    type: Literal["InputIfExists"]
    name: str

    def entry(self) -> Entry:
        return InputIfExists(self.name)


class GraphicsPathEntry(EntryModel):
    type: Literal["GraphicsPath"]
    dirs: tuple[str, ...]
    include_cwd: bool = True

    def entry(self) -> Entry:
        return GraphicsPath(*self.dirs, include_cwd=self.include_cwd)


class MetadataData(Built):
    """`Document.metadata` as data: `{"lang": "en-GB", "pdfstandard": ["A-2b"]}`."""

    lang: str | None = None
    pdfversion: str | None = None
    pdfstandard: tuple[str, ...] = ()
    colorprofiles: dict[str, str] = {}
    extra: dict[str, str] = {}

    def build(self) -> RequireMetadata:
        return RequireMetadata(
            lang=self.lang,
            pdfversion=self.pdfversion,
            pdfstandard=self.pdfstandard,
            colorprofiles=self.colorprofiles,
            extra=self.extra,
        )


class PdfInfoData(Built):
    """`Document.pdf` as data: `{"title": "Rex", "trailer_id": "00112233445566778899AABBCCDDEEFF"}`."""

    title: str | None = None
    author: str | None = None
    subject: str | None = None
    keywords: tuple[str, ...] = ()
    producer: str | None = None
    creator: str | None = None
    created: datetime.datetime | None = None
    modified: datetime.datetime | None = None
    trailer_id: str | None = None
    extra: dict[str, str] = {}

    def build(self) -> PdfInfo:
        return PdfInfo(
            title=self.title,
            author=self.author,
            subject=self.subject,
            keywords=self.keywords,
            producer=self.producer,
            creator=self.creator,
            created=self.created,
            modified=self.modified,
            trailer_id=None if self.trailer_id is None else TrailerId(self.trailer_id),
            extra=self.extra,
        )


def _plain(found: dict[str, object]) -> dict[str, object]:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in found.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]


def metadata_data(metadata: RequireMetadata) -> dict[str, object]:
    """The data `MetadataData` reads back to `metadata`: the keys that are set."""
    return _plain({k: v for k, v in dataclasses.asdict(metadata).items() if v})


def pdf_data(info: PdfInfo) -> dict[str, object]:
    """The data `PdfInfoData` reads back to `info`: the fields that are set, a date as ISO 8601."""
    found: dict[str, object] = {k: v for k, v in dataclasses.asdict(info).items() if v and k != "trailer_id"}
    found |= {k: v.isoformat() for k in ("created", "modified") if (v := getattr(info, k)) is not None}
    if info.trailer_id:
        found["trailer_id"] = info.trailer_id.hex
    return _plain(found)


def item_tag(item: object) -> str:
    """A slot item in data is a string (`Raw`) or an object that names its entry with `"type"`."""
    if isinstance(item, str | Raw):
        return "Raw"
    return str(item.get("type")) if isinstance(item, dict) else type(item).__name__  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


type ItemEntry = Raw | EntryModel
Item = Annotated[
    Annotated[Raw, pydantic.Tag("Raw")]
    | Annotated[PassOptionEntry, pydantic.Tag("PassOption")]
    | Annotated[InputPathEntry, pydantic.Tag("InputPath")]
    | Annotated[InputIfExistsEntry, pydantic.Tag("InputIfExists")]
    | Annotated[GraphicsPathEntry, pydantic.Tag("GraphicsPath")],
    pydantic.Discriminator(item_tag),
]


class PreambleData(pydantic.BaseModel):
    """`PreambleSlots` as data: each slot a list of TeX strings and entry objects."""

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    before_class: tuple[Item, ...] = ()
    before_package: tuple[Item, ...] = ()
    after_package: tuple[Item, ...] = ()

    def slots(self) -> PreambleSlots:
        def item(found: ItemEntry) -> Raw | Entry:
            return found if isinstance(found, Raw) else found.entry()

        return PreambleSlots(
            tuple(map(item, self.before_class)),
            tuple(map(item, self.before_package)),
            tuple(map(item, self.after_package)),
        )


def preamble_data(slots: PreambleSlots) -> dict[str, list[object]]:
    """The data `PreambleData` reads back to `slots`: only the slots that hold something."""

    def item(found: Raw | Entry) -> object:
        match found:
            case Raw():
                return found.tex
            case PassOption():
                fields: dict[str, object] = {"package": found.package, "option": found.option}
            case InputPath():
                fields = {"dirs": list(found.dirs)}
            case InputIfExists():
                fields = {"name": found.name}
            case GraphicsPath():
                fields = {"dirs": list(found.dirs), "include_cwd": found.include_cwd}
        return {"type": type(found).__name__, **fields}

    return {
        slot: [item(found) for found in items]
        for slot, items in (
            ("before_class", slots.before_class),
            ("before_package", slots.before_package),
            ("after_package", slots.after_package),
        )
        if items
    }
