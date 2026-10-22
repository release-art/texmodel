"""Two packages: one calls the other by Python binding, and `\\RequirePackage` follows."""

from texmodel.body import Hole, TexRaw, Whitespace
from texmodel.components import Command, Environment
from texmodel.package import Package
from texmodel.types import Text

base = Package("base-kit", prefix="bk", version="1.0.0", date="2026/10/22", description="The package that is called")


@base.command
class Fact(Command):
    """One fact, set as a paragraph."""

    body = r"\par\noindent #text\par"

    text: Text


@base.environment
class Panel(Environment):
    """A framed panel with a title."""

    children = [Fact.times.any()]
    begin = r"\par\noindent\textbf{#title}\begin{quote}"
    end = r"\end{quote}"

    title: Text


pkg = Package(
    "composed-kit",
    prefix="ck",
    version="1.0.0",
    date="2026/10/22",
    description="Calls base-kit by Python binding",
    whitespace=Whitespace.TRIM,
)


@pkg.command
class Entry(Command):
    """A fact with a rule above it; the fact is base-kit's."""

    text: Text

    def body(self):
        yield TexRaw(r"""
            \par\hrule
            \vspace{1mm}
        """)
        yield Fact.call(Hole("text"))


@pkg.environment
class Section(Environment):
    """A titled panel of entries: base-kit's panel, opened and closed by reference."""

    children = [Entry.times.at_least_one()]
    begin = Panel.open(title=Hole("title"))
    end = Panel.close()

    title: Text


dependencies = [base]
documents = {"composed": pkg.document(Section(Entry("First"), Entry("R&D 50%"), title="Notes"))}
