r"""Package options (§21): what one option is, the l3keys keys that read it, and what a document's setting of it writes.

Every option of a package is a key of the l3keys family named after the package, set only while it loads
(`.usage:n = load`) and processed once by `\ProcessKeyOptions`. The register a key sets is a LaTeX2e one (`\newif`,
`\newlength`, `\newcommand`), so hand-written TeX reads it as usual and the scanner reads its declaration.
"""

import dataclasses
import enum
import typing
from typing import TYPE_CHECKING, Any

from ..errors import DeclarationError
from ..types import Choice, Raw, ValueKind, escape
from .render import RAW_KIND

if TYPE_CHECKING:
    from ..components import AnyValue


@enum.unique
class OptionKind(enum.Enum):
    FLAG = "flag"
    LENGTH = "length"
    CHOICE = "choice"


@dataclasses.dataclass(frozen=True)
class Option:
    """One option as the package declared it, and the value it sets. Two declarations of one name are the same option
    when `same` agrees; the value class and its doc are the first declaration's."""

    name: str
    kind: OptionKind
    default: object
    inverse: str | None
    cs: str | None
    value: "type[AnyValue]"

    @property
    def same(self) -> tuple[object, ...]:
        """What two declarations of the option must agree on."""
        return (self.kind, self.default, self.inverse, self.cs)

    def keys(self, cs: str) -> list[str]:
        """The l3keys lines of this option; `cs` is its register's control sequence, without the backslash."""
        n = self.name
        match self.kind:
            case OptionKind.FLAG:
                out = [f"{n} .legacy_if_set:n = {cs} ,", f"{n} .default:n = true ,", f"{n} .usage:n = load ,"]
                if self.inverse:
                    i = self.inverse
                    out += [
                        f"{i} .legacy_if_set_inverse:n = {cs} ,",
                        f"{i} .default:n = true ,",
                        f"{i} .usage:n = load ,",
                    ]
                return out
            case OptionKind.LENGTH:
                return [
                    f"{n} .code:n = \\setlength {{ \\{cs} }} {{#1}} ,",
                    f"{n} .value_required:n = true ,",
                    f"{n} .usage:n = load ,",
                ]
            case OptionKind.CHOICE:
                keys = [choice_key(m) for m in type(typing.cast("Choice", self.default))]
                return [
                    f"{n} .choice: ,",
                    f"{n} .usage:n = load ,",
                    *(f"{n} / {k} .code:n = \\cs_set_eq:Nc \\{cs} {{ {cs}@{k} }} ," for k in keys),
                ]

    def text(self, value: object) -> str:
        """`key=value` as a document's setting of it writes it in `\\usepackage[...]`."""
        match self.kind:
            case OptionKind.FLAG:
                return f"{self.name}={'true' if value else 'false'}"
            case OptionKind.LENGTH:
                return f"{self.name}={value}"
            case OptionKind.CHOICE:
                return f"{self.name}={choice_key(typing.cast('Choice', value))}"  # a member: `Value` checks it


def choice_key(member: Choice) -> str:
    """The value a document writes for a member: its name, lowercase, `-` for `_` (`A4_LANDSCAPE` is `a4-landscape`)."""
    return member.name.lower().replace("_", "-")


def _member_tex(member: Choice) -> str:
    value = member.value
    return value.tex if isinstance(value, Raw) else escape(str(value))


def _declare_choice(prefix: str, name: str, default: Any, _alias: str | None) -> list[str]:  # noqa: ANN401
    cs, chosen = f"{prefix}{name}", typing.cast("Choice", default)
    return [
        f"\\newcommand{{\\{cs}}}{{{_member_tex(chosen)}}}",
        *(f"\\@namedef{{{cs}@{choice_key(m)}}}{{{_member_tex(m)}}}" for m in type(chosen)),
    ]


def _no_setting(prefix: str, name: str, _value: Any, _alias: str | None) -> str:  # noqa: ANN401
    raise DeclarationError(
        f"\\{prefix}{name}: a package option is set when the package loads, in \\usepackage[...]",
        code="TM-M072",
        path=name,
        hint="give the setting to the Document: it is written in \\usepackage[...]",
    )


def choice_kind(choice: type[Choice]) -> ValueKind:
    """The value kind of a choice option: a macro that expands to the chosen member's TeX."""
    return dataclasses.replace(
        RAW_KIND, name=f"Choice {choice.__name__}", python=choice, declare=_declare_choice, setting=_no_setting
    )
