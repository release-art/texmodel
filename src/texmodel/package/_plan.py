"""A document as lines: the plan a package writes for a `Document`."""

import typing
from collections.abc import Callable, Iterator, Sequence
from typing import TYPE_CHECKING

from .._internal.emit import INDENT, call_line, emit
from .._internal.options import Option
from .._internal.render import (
    addressed,
    undeclared,
)
from ..components import (
    AnyValue,
    Command,
    Environment,
    Node,
    Passthrough,
    control_name,
)
from ..document import OPTION, Document
from ..drift import stamp
from ..errors import DeclarationError, Violation
from ..plan import BEGIN_DOCUMENT, Line, Plan, Span
from ..preamble import Entry, PdfInfo, RequireMetadata
from ..types import Raw

if TYPE_CHECKING:
    from . import Package


def passthroughs(node: Node, path: str) -> Iterator[tuple[str, Passthrough]]:
    """Every `Passthrough` in a tree with its plan path."""
    if isinstance(node, Passthrough):
        yield path, node
    elif isinstance(node, Environment):
        for i, child in enumerate(node.content):
            yield from passthroughs(child, f"{path}/{type(child).__name__}[{i}]")


def document_of(body: Sequence[Node | Document]) -> Document:
    """The `Document` a call gave: one, alone, or the bare nodes of a plain one."""
    given = [b for b in body if isinstance(b, Document)]
    if given and len(body) > 1:
        raise TypeError("a Document is the whole document: give it alone, or give only nodes")
    return given[0] if given else Document(*typing.cast("Sequence[Node]", body))


def tex_of(item: Raw | Entry) -> Raw:
    """The `Raw` a slot item stands for."""
    return item if isinstance(item, Raw) else item.raw()


def node_lines(node: Node, path: str, depth: int = 0) -> Iterator[Line]:
    """The lines a node renders at `depth`; children are indexed within their parent, as `violations()` paths are."""
    if not isinstance(node, Command | Environment):
        yield from (Line(path, tex) for tex in emit(node, depth).splitlines())
        return
    pad = INDENT * depth
    call, found = call_line(node)
    shift = len(pad)  # a multi-line call has no one-line spans
    spans = tuple(Span(arg, start + shift, end + shift) for arg, start, end in found) if "\n" not in call else ()
    yield from (Line(path, tex, spans) for tex in (pad + call).splitlines())
    if isinstance(node, Environment):
        for i, child in enumerate(node.content):
            yield from node_lines(child, f"{path}/{type(child).__name__}[{i}]", depth + 1)
        yield Line(path, f"{pad}\\end{{{control_name(type(node))}}}")


class Loads:
    """The calls that load packages for one root package (a `.sty`, or a document): each package is called once, by its
    first caller, and an adopted one first calls what it declares it needs, so every package loads before what needs it.
    A package asked for twice with different options is an error, unless the root requires it itself: the options the
    root gives are the user's decision and are the ones used."""

    def __init__(self, root: "Package") -> None:
        self.mandated = {p.name: o for p, o in root.requirements}
        self.options: dict[str, tuple[str, ...]] = {}  # what each package is loaded with, in call order
        self.asker: dict[str, str] = {}

    def call(self, package: "Package", options: tuple[str, ...], asker: str) -> list[tuple[str, tuple[str, ...]]]:
        name = package.name
        wanted = self.mandated.get(name, options)
        if name in self.options:
            if set(self.options[name]) != set(wanted):
                raise DeclarationError(
                    f"{name}: {self.asker[name]} loads it with options {list(self.options[name])}, "
                    f"{asker} with {list(wanted)}",
                    code="TM-P013",
                    path=name,
                    hint=f"require it at the top, with the options you want: pkg.require({name}, options=[...])",
                )
            return []
        self.options[name], self.asker[name] = wanted, asker
        needed = [e for p, o in package.requirements for e in self.call(p, o, name)] if package.adopted else []
        return [*needed, (name, wanted)]

    def plain(self, name: str) -> list[tuple[str, tuple[str, ...]]]:
        """A package named by a value's need, which has no options."""
        if name in self.options:
            return []
        self.options[name] = ()
        return [(name, ())]


def setting_line(value: AnyValue) -> str:
    """The line that sets `value` for a document: `\\setlength{\\acGap}{3mm}`, `\\renewcommand{\\acName}{R\\&D}`,
    `\\acDrafttrue`. It is what `Package.plan` writes for each of a `Document`'s `settings`."""
    cls = type(value)
    return cls.__tm_kind__.setting(*addressed(cls.__tm_prefix__, cls.__name__, cls.cs), value.value, cls.colour_name)


def plan_of(
    package: "Package",
    document: Document,
    version: str,
    option_of: Callable[[type], "tuple[Package, Option] | None"],
) -> Plan:
    """The plan of `document` for `package` (`Package.plan`). `option_of` finds the package and option a settings value
    sets, and `version` is the generator's, stamped in the header."""
    preamble, settings, options = document.preamble, document.settings, document.options
    problems = [v for node in document.content for v in node.violations()]
    problems += [
        Violation("TM-M015", path, f"\\{word} is not declared by this package", hint="declare it, or fix the name")
        for i, node in enumerate(document.content)
        for path, passthrough in passthroughs(node, f"{type(node).__name__}[{i}]")
        for word in undeclared(package.prefix, passthrough.tex.tex, package.known_controls)
    ]
    problems += [
        Violation(
            "TM-M015",
            f"preamble.{slot}[{i}]",
            f"\\{word} is not declared by this package",
            hint="declare it, or fix the name",
        )
        for slot, i, item in preamble.items()
        for word in undeclared(package.prefix, tex_of(item).tex, package.known_controls)
    ]
    problems += [
        Violation(
            "TM-C008",
            f"preamble.{slot}[{i}]",
            f"{type(item).__name__} does not belong in {slot}",
            hint=f"put it in {' or '.join(type(item).slots)}",
        )
        for slot, i, item in preamble.items()
        if not isinstance(item, Raw) and slot not in type(item).slots
    ]
    problems += [
        Violation(
            "TM-C009",
            f"preamble.{slot}[{i}]",
            "PdfInfo needs \\DocumentMetadata, which no RequireMetadata in before_class provides",
            hint="add RequireMetadata() to before_class",
        )
        for slot, i, item in preamble.items()
        if isinstance(item, PdfInfo) and not any(isinstance(x, RequireMetadata) for x in preamble.before_class)
    ]
    problems += [
        Violation("TM-C006", f"options[{i}]", f"class option {o!r} must match [A-Za-z0-9][A-Za-z0-9=.-]*")
        for i, o in enumerate(options)
        if not OPTION.fullmatch(o)
    ]
    if problems:
        raise ExceptionGroup("invalid document", [v.error() for v in problems])
    opts = f"[{','.join(options)}]" if options else ""

    def slot(name: str) -> list[Line]:
        return [
            Line(f"preamble.{name}[{i}]", tex)
            for i, raw in enumerate(getattr(preamble, name))
            for tex in tex_of(raw).tex.splitlines()
        ]

    # An option is set where it takes effect, when its package loads: this package's in `\\usepackage[...]`, a
    # base's passed to it first. Every other setting goes right after the package, in the order given.
    routed = [(i, v, option_of(type(v))) for i, v in enumerate(settings)]
    own = [found[1].text(v.value) for _, v, found in routed if found and found[0] is package]
    passed = [
        Line(f"settings[{i}]", f"\\PassOptionsToPackage{{{found[1].text(v.value)}}}{{{found[0].name}}}")
        for i, v, found in routed
        if found and found[0] is not package
    ]
    uses = [
        Line("document", f"\\usepackage[{','.join(o)}]{{{n}}}" if o else f"\\usepackage{{{n}}}")
        for n, o in Loads(package).call(package, tuple(own), "the document")
    ]

    def values() -> list[Line]:
        return [Line(f"settings[{i}]", setting_line(v)) for i, v, found in routed if not found]

    return Plan(
        (
            Line("header", f"% {package.name} document -- {stamp(version)}. Do not edit."),
            *slot("before_class"),
            Line("document", f"\\documentclass{opts}{{{package.document_class}}}"),
            *slot("before_package"),
            *passed,
            *([] if package.builtin else uses),
            *values(),
            *slot("after_package"),
            BEGIN_DOCUMENT,
            *(
                line
                for i, node in enumerate(document.content)
                for line in node_lines(node, f"{type(node).__name__}[{i}]")
            ),
            Line("document", "\\end{document}"),
        )
    )
