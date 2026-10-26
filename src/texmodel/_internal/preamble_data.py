"""Preamble slots as data (`spec`): each entry is a model that names its entry with `"type"`; building the entry is
the check, so what an entry refuses is a data error too."""

import abc
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
)
from ..types import Raw


class EntryModel(pydantic.BaseModel):
    """An entry as data: `{"type": "PassOption", "package": ..., "option": ...}` (§21). Building the entry is the check,
    so a `PdfInfo` key or an `InputIfExists` name that the entry refuses is a data error too."""

    model_config = pydantic.ConfigDict(frozen=True, extra="forbid")

    @abc.abstractmethod
    def entry(self) -> Entry: ...

    @pydantic.model_validator(mode="after")
    def _constructible(self) -> "EntryModel":
        try:
            self.entry()
        except DeclarationError as exc:
            raise ValueError(str(exc)) from exc
        return self


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


class RequireMetadataEntry(EntryModel):
    type: Literal["RequireMetadata"]
    entries: dict[str, str] = {}

    def entry(self) -> Entry:
        return RequireMetadata(**self.entries)


class PdfInfoEntry(EntryModel):
    type: Literal["PdfInfo"]
    entries: dict[str, str] = {}

    def entry(self) -> Entry:
        return PdfInfo(**self.entries)


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
    | Annotated[GraphicsPathEntry, pydantic.Tag("GraphicsPath")]
    | Annotated[RequireMetadataEntry, pydantic.Tag("RequireMetadata")]
    | Annotated[PdfInfoEntry, pydantic.Tag("PdfInfo")],
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
            case RequireMetadata() | PdfInfo():
                fields = {"entries": dict(found.entries)}
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
