r"""tabularray: Tables from an inner and an outer key list, with their styles apart from their cells.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package. It covers
the package and the libraries with names of their own (`booktabs`, `diagbox`, `tikz`); a library is loaded with
`UseTblrLibrary`. The cells are TeX between `Passthrough`s, with `&` and `\\` as written.

```python
from texmodel.std.tabularray import CellSpec, HAlign, HlineSpec, Tblr, TblrInner, cell

Tblr(
    Passthrough(Raw(r"a & b \\")),
    inner=TblrInner(colspec=Raw("ll"), hlines=HlineSpec(), rules=[cell(1, 2, CellSpec(halign=HAlign.RIGHT))]),
)  # \begin{tblr}{colspec=ll,hlines={},cell{1}{2}={halign=r}}
```

Keys that carry arguments (`cell{1}{2}`, `row{odd}`, `hline{1,Z}`) are `Entry` items of the `rules` list, built by
`cell`, `row`, `column`, `hline`, `vline`, `hborder` and `vborder` from a `selector`. Not typed: `colspec` and `rowspec`
(a language of their own), the `amsmath` library's `+matrix` family (an environment name has letters only), the
experimental interfaces (child ids and classes, hooks, public variables) and the `functional` library's functions."""

from ._commands import (
    Addlinespace as Addlinespace,
    Addrowspace as Addrowspace,
    Bottomrule as Bottomrule,
    Cline as Cline,
    Cmidrule as Cmidrule,
    Cmidrulemore as Cmidrulemore,
    DeclareTblrTemplate as DeclareTblrTemplate,
    Diagbox as Diagbox,
    Diagboxthree as Diagboxthree,
    ExpTblrTemplate as ExpTblrTemplate,
    Hborder as Hborder,
    Hline as Hline,
    Midrule as Midrule,
    Morecmidrules as Morecmidrules,
    NewTblrColumnRowType as NewTblrColumnRowType,
    NewTblrColumnType as NewTblrColumnType,
    NewTblrContentCommand as NewTblrContentCommand,
    NewTblrDashStyle as NewTblrDashStyle,
    NewTblrEnviron as NewTblrEnviron,
    NewTblrRowType as NewTblrRowType,
    NewTblrTableCommand as NewTblrTableCommand,
    NewTblrTheme as NewTblrTheme,
    Rline as Rline,
    SetCell as SetCell,
    SetCells as SetCells,
    SetColumn as SetColumn,
    SetColumns as SetColumns,
    SetHline as SetHline,
    SetHlines as SetHlines,
    SetRow as SetRow,
    SetRows as SetRows,
    SetTblrInner as SetTblrInner,
    SetTblrOuter as SetTblrOuter,
    SetTblrStyle as SetTblrStyle,
    SetTblrTemplate as SetTblrTemplate,
    SetTblrTracing as SetTblrTracing,
    SetVline as SetVline,
    SetVlines as SetVlines,
    Specialrule as Specialrule,
    TblrNote as TblrNote,
    Toprule as Toprule,
    UseTblrLibrary as UseTblrLibrary,
    UseTblrTemplate as UseTblrTemplate,
    Vborder as Vborder,
    Vline as Vline,
)
from ._environments import (
    TABLE_BODY as TABLE_BODY,
    Booktabs as Booktabs,
    Longtabs as Longtabs,
    Longtblr as Longtblr,
    TableRow as TableRow,
    Talltabs as Talltabs,
    Talltblr as Talltblr,
    Tblr as Tblr,
    TblrTikzAbove as TblrTikzAbove,
    TblrTikzBelow as TblrTikzBelow,
    expand_of as expand_of,
)
from ._specs import (
    Baseline as Baseline,
    CellSpan as CellSpan,
    CellSpec as CellSpec,
    ColumnSpec as ColumnSpec,
    Dash as Dash,
    HAlign as HAlign,
    HborderSpec as HborderSpec,
    HlineSpec as HlineSpec,
    Index as Index,
    Measure as Measure,
    Mode as Mode,
    PageBreak as PageBreak,
    RowSpec as RowSpec,
    Selector as Selector,
    Span as Span,
    TblrInner as TblrInner,
    TblrOuter as TblrOuter,
    VAlign as VAlign,
    VborderSpec as VborderSpec,
    VlineSpec as VlineSpec,
    cell as cell,
    cells as cells,
    column as column,
    hborder as hborder,
    hline as hline,
    hlines as hlines,
    note as note,
    package as package,
    remark as remark,
    row as row,
    selector as selector,
    vborder as vborder,
    vline as vline,
    vlines as vlines,
)
