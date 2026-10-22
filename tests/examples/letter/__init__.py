"""A letter: environment arguments, nested environments, `Raw`, and a value that needs another package."""

from texmodel.components import Command, Environment, TemplateRef, Value
from texmodel.package import Package
from texmodel.types import Bool, Colour, Gray, Length, Raw, Text

pkg = Package("letter-kit", prefix="lt", version="1.0.0", date="2026/10/22", description="Letters")


@pkg.value
class Indent(Value[Length]):
    """First-line indent; `em` is relative to the font and is kept as written."""

    default = Length("1.5em")


@pkg.value
class Ink(Value[Colour]):
    """Body text colour. Declares `calc` on top of the `xcolor` that colours imply."""

    needs_packages = ("calc",)
    default = Gray(0.2)


@pkg.value
class Draft(Value[Bool]):
    """Mark the letter as a draft."""

    default = False


@pkg.command
class Paragraph(Command):
    """One paragraph of body text."""

    body = r"\par\noindent\hspace{\ltIndent}\textcolor{lt-ink}{#text}\par"

    text: Text


@pkg.command
class Aside(Command):
    """A note set small. The TeX is passed through, not escaped, so it must be trusted."""

    tex: Raw

    def body(self):
        return r"\par{\footnotesize #tex}\par"


@pkg.command
class Signoff(Command):
    """The closing line and the sender's name."""

    body = r"\par\vspace{1cm}\noindent #name\par"

    name: Text


@pkg.environment
class Quote(Environment):
    """A quotation: only paragraphs."""

    begin = r"\begin{quote}"
    end = r"\end{quote}"

    children = [Paragraph * "+"]


@pkg.environment
class Letter(Environment):
    """A letter to someone, with an optional subject line. Arguments belong to the begin body."""

    begin = TemplateRef("letter.begin.tex")
    end = TemplateRef("letter.end.tex")

    children = [Paragraph * "+", Quote * "*", Aside * "?", Signoff]
    recipient: Text
    subject: Text | None = None


invitation = Letter(
    Paragraph("You are invited to a talk on 100% reproducible builds."),
    Quote(Paragraph("A build that cannot be repeated is a rumour.")),
    Aside(Raw(r"\emph{P.S.} Bring a \textsc{laptop}.")),
    Signoff("Grace"),
    recipient="Dr. Hopper",
    subject="Talk: builds",
)

terse = Letter(Paragraph("Thanks!"), Signoff("G."), recipient="All")

documents = {
    "invitation": pkg.document(invitation, settings=[Draft(True), Indent(Length("0pt"))]),
    "terse": pkg.document(terse),
}
