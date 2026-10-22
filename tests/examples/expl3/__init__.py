"""expl3 as a syntax mode: a verbatim library block that a component is defined by, and a body written in expl3."""

from texmodel.body import Cs, Hole, Lit, Seq, Syntax
from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Raw

pkg = Package(
    "expl3-kit",
    prefix="ek",
    version="1.0.0",
    date="2026/10/22",
    description="A library block and an expl3 body",
)

scale = pkg.library(
    "scale",
    r"""
    \fp_new:N \l__ek_scaled_fp
    \newcommand{\ekScaled}[2]{
        \fp_set:Nn \l__ek_scaled_fp { #1 * #2 }
        \fp_eval:n { round ( \l__ek_scaled_fp , 2 ) }
    }
    """,
    syntax=Syntax.EXPL3,
)


@pkg.command
class Scaled(Command):
    """The product of two numbers, rounded to two places; the library block defines it."""

    defined_by = scale
    factor: Raw
    base: Raw


@pkg.command
class Total(Command):
    """A paragraph giving the scaled value; written in expl3, so a space in its text is `~`."""

    factor: Raw
    base: Raw

    def body(self):
        yield Seq(Cs("par", Syntax.EXPL3), Lit("Total: "), Scaled.call(Hole("factor"), Hole("base")))


documents = {"expl3": pkg.document(Total(Raw("2.5"), Raw("3.333")))}
