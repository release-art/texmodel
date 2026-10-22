"""A small algorithm the deck needs and a hand-written `.sty` would hold: the title size that fits a width. The numbers
are invented. The block is expl3 and carried verbatim; the commands declare what it defines."""

from texmodel.body import Cs, Group, Hole, Lit, Seq, Syntax
from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw

pkg = Package("card-deck-fit", prefix="cf", version="1.0.0", date="2026/10/22")

title_size = pkg.library(
    "title-size",
    r"""
    % A title of natural width #1 set in a space of width #2: 12pt scaled to fit, between 8pt and 14pt.
    \fp_new:N \l__cf_size_fp
    \newcommand{\cfFitSize}[2]{
        \fp_set:Nn \l__cf_size_fp { min ( 14 , max ( 8 , 12 * \dim_to_fp:n { #2 } / \dim_to_fp:n { #1 } ) ) }
    }
    \newcommand{\cfTitleSize}{ \fp_eval:n { round ( \l__cf_size_fp , 1 ) } }
    """,
    syntax=Syntax.EXPL3,
)


@pkg.command
class FitSize(Command):
    """Work out the title size for a natural width in an available width."""

    defined_by = title_size
    natural: Raw
    available: Raw


@pkg.command
class TitleSize(Command):
    """The size `FitSize` worked out, in points, to one decimal."""

    defined_by = title_size


@pkg.command
class ShowTitleSize(Command):
    """Work out the size and write it to the log as `texmodel:probe:title-size=...`."""

    natural: Raw
    available: Raw

    def body(self):
        yield FitSize.call(Hole("natural"), Hole("available"))
        yield Seq(Cs("typeout"), Group(Lit("texmodel:probe:title-size="), TitleSize.call()))
