"""A table environment a package owns: the layout is in the `.sty`, a document holds only the rows."""

from collections.abc import Callable
from typing import ClassVar

from ...components import Anywhere, Environment, Passthrough
from ...errors import DeclarationError
from ...package import Package
from ...std import tabularray as t
from ...types import Length, Raw
from ._parts import Look
from ._table import Table, check_cells


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
    outer: t.TblrOuter | None = None
    # `tabularray` takes a mandatory argument, so the environment of the layout is `<name>Tblr` and this one forwards.
    begin = r"\csname\@currenvir Tblr\endcsname[#outer]{}"
    end = r"\csname end\@currenvir Tblr\endcsname"

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        cls.children = [Anywhere(row) for row in cls.rows] or [Anywhere(Passthrough)]
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
        parts = [
            t.NewTblrEnviron(name=Raw(name)),
            t.SetTblrInner(environments=Raw(name), spec=inner),
            t.SetTblrOuter(environments=Raw(name), spec=t.TblrOuter(expand=expand)),
        ]
        pkg.library(f"{cls.__tm_cs__}Layout", "\n".join(p.render() for p in parts))
        return cls

    return register
