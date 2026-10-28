r"""intent: a PDF output intent (PDF/X, PDF/A) declared once, written where LaTeX needs it.

`OutputIntent` gives the `\DocumentMetadata` keys (before `\documentclass`) and the registration of the ICC profile's
output condition. l3pdfmeta knows the condition of only two profile names (`sRGB.icc`, `FOGRA39L_coated.icc`); for any
other it warns and writes no OutputIntent, so PDF/X and PDF/A both fail without an error. Registering under the exact
name the preamble passes is what makes the intent appear.

```python
condition = OutputCondition(
    "FOGRA39L_coated.icc", identifier="FOGRA39", info="Coated FOGRA39 (ISO 12647-2:2004)", colorants=4
)
intent = OutputIntent(condition, standards=(Standard.X4, Standard.A2B), language="en-GB")
slots = intent.slots(directory="res/icc")   # a Document's `preamble=`
intent.declare(pkg, directory="res/icc")    # the registration, in the package's .sty
```
"""

import dataclasses
import enum
import re
from collections.abc import Sequence

from ..body import Syntax
from ..errors import DeclarationError, Violation
from ..package import Package
from ..preamble import PreambleSlots, RequireMetadata
from ..types import Raw

_UNSAFE = re.compile(r"[,=%\\{}#]")
_COLOUR_SPACES = {1: b"GRAY", 3: b"RGB ", 4: b"CMYK"}  # colorants -> the ICC header's data colour space

LIBRARY = r"""
    \clist_map_inline:nn { <<names>> }
      {
        \prop_if_exist:cF { c__pdfmeta_colorprofile_ #1 }
          {
            \prop_const_from_keyval:cn { c__pdfmeta_colorprofile_ #1 }
              {
                ,OutputConditionIdentifier = <<identifier>>
                ,Info                      = <<info>>
                ,RegistryName              = <<registry>>
                ,N                         = <<colorants>>
              }
          }
      }
"""


@enum.unique
class Standard(enum.Enum):
    """A conformance `pdfstandard` names, with the intent subtype `colorprofiles` gives it."""

    X4 = ("X-4", "X", None)
    A2B = ("A-2b", "A", (1, 7))

    @property
    def key(self) -> str:
        return self.value[0]

    @property
    def subtype(self) -> str:
        return self.value[1]

    @property
    def newest(self) -> tuple[int, int] | None:
        """The newest PDF version the standard allows (PDF/A-2 is PDF 1.7 at most; the engine writes 2.0 unasked)."""
        return self.value[2]


def _allows(version: str | None, newest: tuple[int, int]) -> bool:
    """Whether `version` ("1.7") is stated and no newer than `newest`."""
    match = re.fullmatch(r"(\d+)\.(\d+)", version or "")
    return bool(match) and (int(match[1]), int(match[2])) <= newest


@dataclasses.dataclass(frozen=True)
class OutputCondition:
    """An ICC profile and the output condition l3pdfmeta writes for it. `profile` is the file name as the preamble
    passes it; `colorants` is the number of colour channels (1, 3 or 4)."""

    profile: str
    identifier: str
    info: str
    registry: str = "http://www.color.org"
    colorants: int = 4

    def __post_init__(self) -> None:
        for name in ("profile", "identifier", "info", "registry"):
            value: str = getattr(self, name)
            if not value or _UNSAFE.search(value) or (name == "profile" and re.search(r"\s", value)):
                raise DeclarationError(
                    f"OutputCondition.{name}={value!r}: not empty, no `, = % \\ {{ }} #` (and no space in a profile)",
                    code="TM-M048",
                    path=name,
                    hint="these are keys of a key=value list the TeX kernel reads",
                )
        if self.colorants not in _COLOUR_SPACES:
            raise DeclarationError(
                f"OutputCondition.colorants={self.colorants!r}: 1, 3 or 4", code="TM-M049", path="colorants"
            )

    def check_profile(self, data: bytes) -> list[Violation]:
        """What the profile file's header says against this condition: an ICC profile at all (a truncated file or a
        Git LFS pointer is not), and the colour space of `colorants`."""
        if len(data) < 128 or data[36:40] != b"acsp":
            return [
                Violation(
                    "TM-C014",
                    self.profile,
                    "not an ICC profile (no `acsp` signature)",
                    hint="a truncated file or an LFS pointer?",
                )
            ]
        space = data[16:20]
        if space != _COLOUR_SPACES[self.colorants]:
            return [
                Violation(
                    "TM-C015",
                    self.profile,
                    f"colour space {space.decode('ascii', 'replace')!r}, but {self.colorants} colorants",
                    hint=f"a profile of {_COLOUR_SPACES[self.colorants].decode()!r}",
                )
            ]
        return []


@dataclasses.dataclass(frozen=True)
class OutputIntent:
    """The conformances a document claims, each with an intent of the same condition, in one `\\DocumentMetadata`
    (`pdfx` cannot claim PDF/X-4 and PDF/A-2b together)."""

    condition: OutputCondition
    standards: Sequence[Standard] = ()
    language: str | None = None
    pdf_version: str | None = None

    def __post_init__(self) -> None:
        for name in ("language", "pdf_version"):
            value: str | None = getattr(self, name)
            if value is not None and (not value or _UNSAFE.search(value)):
                raise DeclarationError(
                    f"OutputIntent.{name}={value!r}: not empty, no `, = % \\ {{ }} #`", code="TM-M048", path=name
                )
        for standard in self.standards:
            if standard.newest is not None and not _allows(self.pdf_version, standard.newest):
                raise DeclarationError(
                    f"OutputIntent: {standard.key} is PDF {'.'.join(map(str, standard.newest))} at most, "
                    f"pdf_version is {self.pdf_version!r}",
                    code="TM-M050",
                    path="pdf_version",
                    hint=f"pdf_version={'.'.join(map(str, standard.newest))!r}: the engine writes 2.0 unasked",
                )

    def keys(self, directory: str = "") -> dict[str, str]:
        """The `\\DocumentMetadata` keys, in the order a document writes them. `directory` is where the profile is."""
        path = f"{directory.rstrip('/')}/{self.condition.profile}" if directory else self.condition.profile
        out: dict[str, str] = {}
        if self.language:
            out["lang"] = self.language
        if self.standards:
            out["pdfstandard"] = ",".join(s.key for s in self.standards)
        if self.pdf_version:
            out["pdfversion"] = self.pdf_version
        if self.standards:  # `subtype=path` pairs: the bare file name is a key without a value, and writes no intent
            out["colorprofiles"] = ",".join(
                f"{kind}={path}" for kind in dict.fromkeys(s.subtype for s in self.standards)
            )
        return out

    def slots(self, directory: str = "") -> PreambleSlots:
        """What a document starts with: the metadata, before `\\documentclass`."""
        return PreambleSlots(before_class=(RequireMetadata(**self.keys(directory)),))

    def declare(self, package: Package, directory: str = "") -> None:
        """Register the condition for the profile under both spellings a document may reach it by: the bare file name
        and `directory/name`. A block of the package's `.sty`, `output-intent`."""
        c = self.condition
        names = [c.profile, *([f"{directory.rstrip('/')}/{c.profile}"] if directory else [])]
        package.library(
            "output-intent",
            LIBRARY,
            syntax=Syntax.EXPL3,
            fill={
                "names": Raw(",".join(names)),
                "identifier": Raw(c.identifier.replace(" ", "~")),
                "info": Raw(c.info.replace(" ", "~")),
                "registry": Raw(c.registry),
                "colorants": Raw(str(c.colorants)),
            },
        )


__all__ = ["LIBRARY", "OutputCondition", "OutputIntent", "Standard"]
