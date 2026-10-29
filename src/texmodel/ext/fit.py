r"""fit: a short line of text set to fit a band, at sizes that are shared across the whole document.

Titles are fitted to the measure and the band's height, and every title that can reach the target takes one main size,
so a deck reads as one design. A few shared smaller sizes serve only the titles that cannot reach it, and no size is
ever below the floor. Each title is measured in one run and fitted in the next (`ext.recorded` carries the widths), and
every title sits on one baseline, below the deck's tallest ascent.

```python
fit = Fit("Title", target=Length("5mm"), floor=Length("3mm"), room=Length("9mm"), reduced_sizes=2)
record, set_title, *values = fit.declare(pkg)       # \apRecordTitle{text}, \apFitTitle{name}{text}
```

`choose_sizes` is the rule in Python, the oracle for the TeX. A title wider than the measure at the floor is named in a
warning: there is no wrapping, so it overflows.
"""

import dataclasses
import math
import re
from collections.abc import Sequence
from typing import Any, NamedTuple

from ..body import Syntax
from ..components import Command, Value, field
from ..errors import DeclarationError
from ..package import Package
from ..types import Length, Raw
from .recorded import APPEND, LENGTHS, Recorded

_NAME = re.compile(r"[A-Z][A-Za-z]*")

# The two public lengths are `\newlength`, as every `Value[Length]` is, so the scanner (`declared`) reads them.
LIBRARY = r"""
    \newlength { \<<p>><<n>>Size }
    \newlength { \<<p>><<n>>LineSize }
    \dim_new:N \l_<<m>>_width_dim
    \dim_new:N \l_<<m>>_ascent_dim
    \dim_new:N \l_<<m>>_descent_dim
    \dim_new:N \l_<<m>>_height_dim
    \dim_new:N \l_<<m>>_up_dim
    \dim_new:N \l_<<m>>_down_dim
    \tl_new:N \l_<<m>>_name_tl
    \clist_new:N \l_<<m>>_widths_clist
    \seq_new:N \l_<<m>>_short_seq
    \fp_new:N \l_<<m>>_cap_fp
    \fp_new:N \l_<<m>>_target_fp
    \fp_new:N \l_<<m>>_own_fp
    \fp_new:N \l_<<m>>_each_fp
    \fp_new:N \l_<<m>>_main_fp
    \fp_new:N \l_<<m>>_low_fp
    \fp_new:N \l_<<m>>_upper_fp
    \fp_new:N \l_<<m>>_best_fp
    \fp_new:N \l_<<m>>_size_fp
    \fp_new:N \l_<<m>>_line_fp
    \cs_new:Npn \<<m>>_treat:n #1 { <<treatment>> }
    \cs_new_protected:Npn \<<m>>_measure:n #1
      {
        \settowidth { \l_<<m>>_width_dim } { \<<m>>_treat:n {#1} }
        \settoheight { \l_<<m>>_ascent_dim } { \<<m>>_treat:n {#1} }
        \settodepth { \l_<<m>>_descent_dim } { \<<m>>_treat:n {#1} }
      }
    \cs_new_protected:Npn \<<m>>_decide:
      {
        \fp_set:Nn \l_<<m>>_cap_fp { ( <<ref>> ) * \<<p>><<n>>Room / \l_<<m>>_height_dim }
        \fp_set:Nn \l_<<m>>_target_fp { max ( \<<p>><<n>>Floor , \<<p>><<n>>Target ) }
        \fp_set:Nn \l_<<m>>_own_fp
          { min ( ( <<ref>> ) * \linewidth / ( \dim_use:N \l_<<m>>_width_dim ) , \l_<<m>>_cap_fp ) }
        \clist_set:Nx \l_<<m>>_widths_clist { \<<p>><<n>>Widths }
        \fp_set:Nn \l_<<m>>_main_fp { inf }
        \seq_clear:N \l_<<m>>_short_seq
        \clist_map_inline:Nn \l_<<m>>_widths_clist
          {
            \fp_set:Nn \l_<<m>>_each_fp
              { min ( ( <<ref>> ) * \linewidth / ( ##1 ) , \l_<<m>>_cap_fp ) }
            \fp_compare:nNnTF \l_<<m>>_each_fp < \l_<<m>>_target_fp
              { \seq_put_right:Nx \l_<<m>>_short_seq { \fp_use:N \l_<<m>>_each_fp } }
              { \fp_set:Nn \l_<<m>>_main_fp { min ( \l_<<m>>_main_fp , \l_<<m>>_each_fp ) } }
          }
        \fp_set:Nn \l_<<m>>_low_fp { inf }
        \fp_set:Nn \l_<<m>>_upper_fp { inf }
        \seq_if_empty:NF \l_<<m>>_short_seq
          {
            \seq_sort:Nn \l_<<m>>_short_seq
              { \fp_compare:nNnTF {##1} < {##2} { \sort_return_swapped: } { \sort_return_same: } }
            \fp_set:Nn \l_<<m>>_low_fp { \seq_item:Nn \l_<<m>>_short_seq { -1 } }
            \fp_set_eq:NN \l_<<m>>_upper_fp \l_<<m>>_low_fp
            \int_compare:nNnT { <<reduced>> } > { 1 }
              {
                \fp_zero:N \l_<<m>>_best_fp
                \seq_map_indexed_inline:Nn \l_<<m>>_short_seq
                  {
                    \fp_compare:nNnT { ##1 * ( ##2 - \l_<<m>>_low_fp ) } > \l_<<m>>_best_fp
                      {
                        \fp_set:Nn \l_<<m>>_best_fp { ##1 * ( ##2 - \l_<<m>>_low_fp ) }
                        \fp_set:Nn \l_<<m>>_upper_fp { ##2 }
                      }
                  }
              }
          }
        \int_compare:nNnTF { <<reduced>> } = { 0 }
          {
            \fp_set:Nn \l_<<m>>_size_fp { min ( \l_<<m>>_main_fp , \l_<<m>>_low_fp , \l_<<m>>_own_fp ) }
            \fp_set_eq:NN \l_<<m>>_line_fp \l_<<m>>_size_fp
          }
          {
            \fp_compare:nNnTF \l_<<m>>_own_fp < \l_<<m>>_target_fp
              {
                \fp_compare:nNnTF \l_<<m>>_own_fp < \l_<<m>>_upper_fp
                  { \fp_set:Nn \l_<<m>>_size_fp { min ( \l_<<m>>_low_fp , \l_<<m>>_own_fp ) } }
                  { \fp_set_eq:NN \l_<<m>>_size_fp \l_<<m>>_upper_fp }
              }
              { \fp_set:Nn \l_<<m>>_size_fp { min ( \l_<<m>>_main_fp , \l_<<m>>_own_fp ) } }
            \fp_set_eq:NN \l_<<m>>_line_fp \l_<<m>>_main_fp
            \fp_compare:nNnT \l_<<m>>_line_fp = { inf }
              { \fp_set_eq:NN \l_<<m>>_line_fp \l_<<m>>_upper_fp }
            \fp_compare:nNnT \l_<<m>>_line_fp = { inf }
              { \fp_set_eq:NN \l_<<m>>_line_fp \l_<<m>>_size_fp }
            \fp_compare:nNnT \l_<<m>>_line_fp < \l_<<m>>_size_fp
              { \fp_set_eq:NN \l_<<m>>_line_fp \l_<<m>>_size_fp }
          }
        \fp_set:Nn \l_<<m>>_size_fp { max ( \l_<<m>>_size_fp , \<<p>><<n>>Floor ) }
        \fp_set:Nn \l_<<m>>_line_fp { max ( \l_<<m>>_line_fp , \<<p>><<n>>Floor ) }
        \dim_gset:Nn \<<p>><<n>>Size { \fp_to_dim:N \l_<<m>>_size_fp }
        \dim_gset:Nn \<<p>><<n>>LineSize { \fp_to_dim:N \l_<<m>>_line_fp }
        \fp_compare:nNnT { ( <<ref>> ) * \linewidth / \l_<<m>>_width_dim } < { \<<p>><<n>>Floor }
          {
            \PackageWarning { <<package>> }
              {
                Title~`\l_<<m>>_name_tl'~does~not~fit~its~measure~even~at~the\MessageBreak
                floor,~and~overflows~it~by~
                \fp_eval:n
                  { round ( ( \l_<<m>>_width_dim * \<<p>><<n>>Floor / ( <<ref>> ) - \linewidth ) / 1mm , 1 ) }
                ~mm
              }
          }
        \fp_compare:nNnT \l_<<m>>_size_fp < \l_<<m>>_line_fp
          {
            \PackageInfo { <<package>> }
              {
                Title~`\l_<<m>>_name_tl'~is~set~at~a~reduced~size~of~
                \fp_eval:n { round ( \l_<<m>>_size_fp / 1mm , 2 ) } ~mm;\MessageBreak
                the~deck's~main~size~is~\fp_eval:n { round ( \l_<<m>>_line_fp / 1mm , 2 ) } ~mm
              }
          }
      }
    \newcommand{\<<p>>Record<<n>>}[1]{%
      \begingroup
        \fontsize{<<ref>>}{<<ref>>}\selectfont
        \tl_trim_spaces_apply:nN {#1} \<<m>>_measure:n
        \<<p>>Record<<n>>Widths{\l_<<m>>_width_dim}%
        \<<p>>Record<<n>>Ascent{\l_<<m>>_ascent_dim}%
        \<<p>>Record<<n>>Descent{\l_<<m>>_descent_dim}%
      \endgroup
    }
    \newcommand{\<<p>>Fit<<n>>}[2]{%
      \begingroup
        \tl_set:Nn \l_<<m>>_name_tl {#1}
        \fontsize{<<ref>>}{<<ref>>}\selectfont
        \tl_trim_spaces_apply:nN {#2} \<<m>>_measure:n
        \dim_compare:nNnT { \<<p>><<n>>Ascent } > \l_<<m>>_ascent_dim
          { \dim_set_eq:NN \l_<<m>>_ascent_dim \<<p>><<n>>Ascent }
        \dim_compare:nNnT { \<<p>><<n>>Descent } > \l_<<m>>_descent_dim
          { \dim_set_eq:NN \l_<<m>>_descent_dim \<<p>><<n>>Descent }
        \dim_set:Nn \l_<<m>>_height_dim { \l_<<m>>_ascent_dim + \l_<<m>>_descent_dim }
        \bool_lazy_and:nnTF
          { \dim_compare_p:nNn \l_<<m>>_width_dim > \c_zero_dim }
          { \dim_compare_p:nNn \l_<<m>>_height_dim > \c_zero_dim }
          {
            \<<m>>_decide:
            \dim_set:Nn \l_<<m>>_up_dim
              { \fp_to_dim:n { \l_<<m>>_ascent_dim * \<<p>><<n>>LineSize / ( <<ref>> ) } }
            \dim_set:Nn \l_<<m>>_down_dim
              { \fp_to_dim:n { \l_<<m>>_descent_dim * \<<p>><<n>>LineSize / ( <<ref>> ) } }
            \fontsize { \<<p>><<n>>Size } { \<<p>><<n>>Size } \selectfont
            \raisebox { \c_zero_dim } [ \l_<<m>>_up_dim ] [ \l_<<m>>_down_dim ]
              { \tl_trim_spaces_apply:nN {#2} \<<m>>_treat:n }
          }
          { \tl_trim_spaces_apply:nN {#2} \<<m>>_treat:n }
      \endgroup
    }
"""


def choose_sizes(
    each: Sequence[float], own: float, *, target: float, floor: float, reduced_sizes: int
) -> tuple[float, float]:
    """The rule the TeX applies, in Python: `(size, line_size)` for a title whose own fit is `own`, in a document where
    every title's fit is in `each` (the deck's recorded widths, each already capped by the band). `size` is what the
    title is set at, `line_size` the size the deck's baseline belongs to.

    A title that reaches the target takes the main size, the smallest fit among those that do. The others are shared
    among at most `reduced_sizes` sizes (0: one size for all); with two, the split puts the first `j` in the upper
    group, the `j` that maximises `j * (o_j - o_n)` over the fits sorted largest first. The floor binds both."""
    goal = max(floor, target)
    main = min((e for e in each if e >= goal), default=math.inf)
    short = sorted((e for e in each if e < goal), reverse=True)
    low = short[-1] if short else math.inf
    upper = low
    if short and reduced_sizes > 1:
        best = 0.0
        for index, value in enumerate(short, 1):
            if (score := index * (value - low)) > best:
                best, upper = score, value
    if reduced_sizes == 0:
        size = line = min(main, low, own)
    else:
        size = (min(low, own) if own < upper else upper) if own < goal else min(main, own)
        line = main
        if line == math.inf:
            line = upper
        if line == math.inf:
            line = size
        line = max(line, size)
    return max(size, floor), max(line, floor)


class FitParts(NamedTuple):
    """What `Fit.declare` registers: the commands, the lengths a document may set, and the sizes the last fit chose."""

    record: type[Command]
    fit: type[Command]
    target: type[Value[Any]]
    floor: type[Value[Any]]
    room: type[Value[Any]]
    size: type[Value[Any]]
    line_size: type[Value[Any]]


@dataclasses.dataclass(frozen=True)
class Fit:
    """Titles fitted to a band: `name` (CamelCase letters), `target` the size a title reaches for, `floor` the size
    below which none goes, `room` the band's height; these three are `Value`s a document may set. `treatment` is the one
    way a title is set, TeX with `#1` for its text: it is measured and drawn alike. `reduced_sizes` is how many shared
    smaller sizes there are (0, 1 or 2) and `reference` the size titles are measured at, which cancels out."""

    name: str
    target: Length
    floor: Length
    room: Length
    treatment: Raw = Raw("#1")  # noqa: RUF009  # an immutable value
    reduced_sizes: int = 2
    reference: Length = Length("10mm")  # noqa: RUF009

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name):
            raise DeclarationError(
                f"Fit.name={self.name!r}: capital letter first, letters only", code="TM-M060", path="name"
            )
        if self.reduced_sizes not in (0, 1, 2):
            raise DeclarationError(
                f"Fit.reduced_sizes={self.reduced_sizes!r}: 0, 1 or 2", code="TM-M061", path="reduced_sizes"
            )
        for key in ("target", "floor", "room", "reference"):
            if getattr(self, key).inches <= 0:
                raise DeclarationError(f"Fit.{key}={getattr(self, key)}: a size", code="TM-M062", path=key)
        if self.floor.inches > self.target.inches:
            raise DeclarationError("Fit: the floor is above the target", code="TM-M062", path="floor")

    def declare(self, package: Package) -> FitParts:
        """The three records (ascent, descent, widths), the block, the commands `Record<Name>{text}` and
        `Fit<Name>{name}{text}`, and the values: `Target`, `Floor` and `Room`, which a document may set, and `Size`
        and `LineSize`, which the last fit set."""
        if not package.prefix:
            raise DeclarationError(f"Fit {self.name}: the package has no prefix", code="TM-M063", path=package.name)
        Recorded(f"{self.name}Ascent").declare(package)
        Recorded(f"{self.name}Descent").declare(package)
        Recorded(f"{self.name}Widths", kind=LENGTHS, fold=APPEND).declare(package)
        values = {
            suffix: package.make_value(f"{self.name}{suffix}", Length, doc, default=getattr(self, suffix.lower()))
            for suffix, doc in (
                ("Target", "The size a title reaches for."),
                ("Floor", "The size below which no title goes."),
                ("Room", "The height of the band a title is set in."),
            )
        }
        lib = package.library(
            f"fit-{self.name}",
            LIBRARY,
            syntax=Syntax.EXPL3,
            fill={
                "p": Raw(package.prefix),
                "n": Raw(self.name),
                "m": Raw(f"{package.prefix}_{self.name}"),
                "package": Raw(package.name),
                "treatment": self.treatment,
                "ref": Raw(str(self.reference)),
                "reduced": Raw(str(self.reduced_sizes)),
            },
        )

        text = (Raw, field())
        return FitParts(
            package.make_command(
                f"Record{self.name}", f"Measure a {self.name} for the deck.", fields={"text": text}, defined_by=lib
            ),
            package.make_command(
                f"Fit{self.name}",
                f"Set a {self.name} to fit its band.",
                fields={"name": (Raw, field()), "text": text},
                defined_by=lib,
            ),
            values["Target"],
            values["Floor"],
            values["Room"],
            package.make_value(f"{self.name}Size", Length, "The size the last title was set at.", defined_by=lib),
            package.make_value(
                f"{self.name}LineSize", Length, "The main size, which the deck's baseline belongs to.", defined_by=lib
            ),
        )


__all__ = ["LIBRARY", "Fit", "FitParts", "choose_sizes"]
