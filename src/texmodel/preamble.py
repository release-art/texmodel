"""Typed preamble entries (§21a 10, G3): each renders to one `Raw` and knows which `PreambleSlots` slots it may sit in.

```python
PreambleSlots(
    before_class=(RequireMetadata(lang="en-GB", pdfstandard="A-2b"),),
    before_package=(InputPath("res/"), PassOption("xcolor", "table")),
    after_package=(GraphicsPath("images/"),),
)
```
"""

import dataclasses
from typing import ClassVar

from .types import Raw

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


type Entry = PassOption | InputPath | GraphicsPath | RequireMetadata


def tex_of(item: Raw | Entry) -> Raw:
    """The `Raw` a slot item stands for."""
    return item if isinstance(item, Raw) else item.raw()
