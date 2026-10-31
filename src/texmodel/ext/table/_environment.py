"""A table environment a package owns: the layout is in the `.sty`, a document holds only the rows."""

import textwrap
from collections.abc import Callable
from typing import ClassVar

from ...components import Anywhere, Environment, Passthrough
from ...errors import DeclarationError
from ...package import Package
from ...std import tabularray as t
from ...types import Length, Macro, Name, NameList, Raw
from ._parts import Look
from ._table import Table, check_cells

_FORWARD_BEGIN = r"\csname\@currenvir Tblr\endcsname[#outer]{}"
_FORWARD_END = r"\csname end\@currenvir Tblr\endcsname"
# The register of the item just set: one per use, as the host keeps the call and sets the box later.
_ITEM_BOX = r"\csname\@currenvir Box\arabic{\@currenvir Boxes}\endcsname"


def _collect_begin() -> str:
    r"""The table is set into a fresh box of its own; `\minipage` and not `\begin{minipage}`, which would change
    `\@currenvir`, the name the layout is found by."""
    return textwrap.dedent(rf"""
        \stepcounter{{\@currenvir Boxes}}%
        \expandafter\newsavebox{_ITEM_BOX}%
        \global\expandafter\setbox{_ITEM_BOX}\hbox\bgroup\minipage{{\linewidth}}%
        {_FORWARD_BEGIN}""").strip()


def _collect_end(collect: Macro) -> str:
    r"""Close the box and call the host's macro with `\usebox{<that box>}` as its last argument."""
    return textwrap.dedent(rf"""
        {_FORWARD_END}%
        \endminipage\egroup
        \edef\@tempa{{\unexpanded{{{collect.tex}}}{{\noexpand\usebox{{\expandafter\noexpand{_ITEM_BOX}}}}}}}%
        \@tempa""").strip()


class TableEnvironment(Environment, abstract=True):
    r"""A table whose layout the package owns, declared with class attributes and registered by `declare(pkg)`.

    `columns` is a `TableRow` class that carries the `Col`s, `rows` the row commands the table holds (any `TableRow`
    classes, whatever their fields), `look`, `width` and `blocks` as in `Table`. A subclass inherits what it does not
    set. The document writes `\begin{acProfile}[caption=...]` and the rows; the optional argument is the table's
    outer keys (caption, label, notes), which belong to the document."""

    columns: ClassVar[type[t.TableRow] | None] = None
    rows: ClassVar[tuple[type[t.TableRow], ...]] = ()
    look: ClassVar[Look] = Look.BOOKTABS
    width: ClassVar[Length | None] = None
    blocks: ClassVar[bool] = False
    collect: ClassVar[Macro | None] = None
    outer: t.TblrOuter | None = None
    # `tabularray` takes a mandatory argument, so the environment of the layout is `<name>Tblr` and this one forwards.
    begin = _FORWARD_BEGIN
    end = _FORWARD_END

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        cls.children = [Anywhere(row) for row in cls.rows] or [Anywhere(Passthrough)]
        if cls.collect is not None:  # the metaclass has taken `begin` and `end`: a class's own are in `__tm_tex__`
            cls.__dict__["__tm_tex__"].update(begin=_collect_begin(), end=_collect_end(cls.collect))
        super().__pydantic_init_subclass__(**kwargs)  # pyright: ignore[reportArgumentType]


def declare[E: type[TableEnvironment]](pkg: Package) -> Callable[[E], E]:
    """Register a table environment in `pkg` and write its layout into the `.sty`. The row commands are registered
    before it (in `pkg` or a package it requires)."""

    def register(cls: E) -> E:
        where = cls.__name__
        if cls.columns is None:
            raise DeclarationError(f"{where}: no columns", code="TM-M088", path=where, hint="set columns = <row class>")
        unregistered = [r.__name__ for r in cls.rows if not hasattr(r, "__tm_cs__")]
        if not cls.rows or unregistered:
            raise DeclarationError(
                f"{where}: rows {unregistered or '()'} are not registered row commands",
                code="TM-M087",
                path=where,
                hint="set rows = (RowClass, ...) and register each with its package first",
            )
        layout = Table(cls.columns, [], header=False, look=cls.look, width=cls.width, blocks=cls.blocks)
        check_cells(cls.columns, len(layout.columns), [(f"{where}.rows", r) for r in cls.rows])
        pkg.environment(cls)
        name = f"{cls.__tm_cs__}Tblr"
        inner = layout._node(every=True).inner  # pyright: ignore[reportPrivateUsage]
        expand = Raw("".join(rf"\{r.__tm_cs__}" for r in cls.rows))
        counter = [rf"\newcounter{{{cls.__tm_cs__}Boxes}}"] if cls.collect is not None else []
        parts = [
            t.NewTblrEnviron(name=Name(name)),
            t.SetTblrInner(environments=NameList(name), spec=inner),
            t.SetTblrOuter(environments=NameList(name), spec=t.TblrOuter(expand=expand)),
        ]
        pkg.library(f"{cls.__tm_cs__}Layout", "\n".join([*counter, *(p.render() for p in parts)]))
        return cls

    return register
