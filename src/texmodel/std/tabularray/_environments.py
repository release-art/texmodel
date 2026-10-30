"""Table rows and the table environments."""

import re
from collections.abc import Iterable
from typing import Any

from texmodel._internal.render import newcommand_fits
from texmodel.components import Anywhere, Command, Environment, Node, Passthrough, control_name
from texmodel.errors import DeclarationError, Violation
from texmodel.types import Raw

from ._commands import (
    Addlinespace,
    Addrowspace,
    Bottomrule,
    Cline,
    Cmidrule,
    Cmidrulemore,
    Diagbox,
    Diagboxthree,
    Hborder,
    Hline,
    Midrule,
    Morecmidrules,
    Rline,
    SetCell,
    SetCells,
    SetColumn,
    SetColumns,
    SetHline,
    SetHlines,
    SetRow,
    SetRows,
    SetVline,
    SetVlines,
    Specialrule,
    TblrNote,
    Toprule,
    Vborder,
    Vline,
)
from ._specs import TblrInner, TblrOuter, package

# --- the environments ------------------------------------------------------------------------------------------------


class TableRow(Command, abstract=True):
    r"""A row a package writes as a command, cells separated by `&` and ended by `\\`: the table expands it before it
    splits the body, so the table lists its commands in `expand` (`expand_of`; a `Table` does it). A subclass has
    mandatory arguments only; without a `body`, each field is one cell, in order (`#icon & #label & #value \\`).
    A row command that calls another lists both."""

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        if not kwargs.get("abstract") and not any("body" in k.__dict__.get("__tm_tex__", {}) for k in cls.__mro__):
            cls.__tm_tex__["body"] = " & ".join(f"#{n}" for n in cls.model_fields) + r" \\"
        super().__pydantic_init_subclass__(**kwargs)
        if not kwargs.get("abstract") and (
            any(a.optional for a in cls.__tm_args__) or not newcommand_fits(cls.__tm_args__)
        ):
            raise DeclarationError(
                f"{cls.__qualname__}: a row command takes mandatory arguments in braces only",
                code="TM-M084",
                path=cls.__name__,
                hint="tabularray expands a plain \\newcommand: an optional or token argument is not expanded",
            )


def expand_of(rows: Iterable[Node]) -> Raw | None:
    r"""The `expand` key for these table children: the commands of the `TableRow`s among them, in order of first use."""
    names = dict.fromkeys(rf"\{control_name(type(r))}" for r in rows if isinstance(r, TableRow))
    return Raw("".join(names)) if names else None


def _expanded(table: Environment, path: str) -> list[Violation]:
    """Every row command of a table is in its `expand` (`TM-C027`): otherwise tabularray splits the body at the `&`
    inside the command and fails with a misplaced alignment tab."""
    outer = getattr(table, "outer", None)
    listed = set(
        re.findall(r"\\[A-Za-z@]+", " ".join(str(getattr(outer, k, None) or "") for k in ("expand", "expand_plus")))
    )
    return [
        Violation(
            "TM-C027",
            f"{path}/{type(row).__name__}[{i}]",
            f"{type(row).__name__}: \\{control_name(type(row))} is not in the table's expand",
            hint="TblrOuter(expand=expand_of(rows))",
        )
        for i, row in enumerate(table.content)
        if isinstance(row, TableRow) and rf"\{control_name(type(row))}" not in listed
    ]


TABLE_BODY = [
    Anywhere(Passthrough),
    Anywhere(TableRow),
    *map(
        Anywhere,
        (
            Hline,
            Cline,
            Vline,
            Rline,
            Hborder,
            Vborder,
            SetHline,
            SetHlines,
            SetVline,
            SetVlines,
            SetCell,
            SetCells,
            SetRow,
            SetRows,
            SetColumn,
            SetColumns,
            TblrNote,
            Toprule,
            Midrule,
            Bottomrule,
            Cmidrule,
            Cmidrulemore,
            Morecmidrules,
            Specialrule,
            Addlinespace,
            Addrowspace,
            Diagbox,
            Diagboxthree,
        ),
    ),
]


@package.environment
class Tblr(Environment):
    r"""A table: `\begin{tblr}[outer]{inner}`."""

    cs = "tblr"
    children = TABLE_BODY
    checks = [_expanded]
    outer: TblrOuter | None = None
    inner: TblrInner


@package.environment
class Longtblr(Environment):
    r"""A table that breaks over pages, with a caption, notes and repeated heads and feet."""

    cs = "longtblr"
    children = TABLE_BODY
    checks = [_expanded]
    outer: TblrOuter | None = None
    inner: TblrInner


@package.environment
class Talltblr(Environment):
    r"""A table with a caption and notes that stays on a page (it can go in a float)."""

    cs = "talltblr"
    children = TABLE_BODY
    checks = [_expanded]
    outer: TblrOuter | None = None
    inner: TblrInner


@package.environment
class Booktabs(Environment):
    r"""A table with `booktabs` rules and no row padding (`booktabs` library)."""

    cs = "booktabs"
    children = TABLE_BODY
    checks = [_expanded]
    outer: TblrOuter | None = None
    inner: TblrInner


@package.environment
class Longtabs(Environment):
    r"""A long `booktabs` table (`booktabs` library)."""

    cs = "longtabs"
    children = TABLE_BODY
    checks = [_expanded]
    outer: TblrOuter | None = None
    inner: TblrInner


@package.environment
class Talltabs(Environment):
    r"""A tall `booktabs` table (`booktabs` library)."""

    cs = "talltabs"
    children = TABLE_BODY
    checks = [_expanded]
    outer: TblrOuter | None = None
    inner: TblrInner


@package.environment
class TblrTikzBelow(Environment):
    r"""TikZ code drawn below the table that follows (`tikz` library): nodes `table`, `<i>-<j>`, `h<i>`, `v<j>`."""

    cs = "tblrtikzbelow"
    children = [Anywhere(Passthrough)]


@package.environment
class TblrTikzAbove(Environment):
    r"""TikZ code drawn above the table that follows (`tikz` library)."""

    cs = "tblrtikzabove"
    children = [Anywhere(Passthrough)]
