"""Unit tests of generated code with stubbed dependencies (§21).

Two tiers. The fast tier needs no TeX: `expand(node, stubs=[Fact])` walks the bodies the generator wrote, with the
node's field values, and returns the text and the `Call` of every stubbed component, in order. The TeX tier is
`Package.test_document(node, stub=[Fact])`: the real packages, each stub replaced by a macro that writes
`texmodel:probe:callN=<call>` to the log, which `texmodel.run.testkit.run_probes` reads back as `Call`s. Both give the
same `Call`s for the same node, so a test asserts what a component passes on, not a PDF. Layout is not covered.

```python
calls = [c for c in expand(card, stubs=[Fact]) if isinstance(c, Call)]
assert calls == [Call("bkFact", ("First",)), Call("bkFact", ("R\\&D 50\\%",))]
```

A call's arguments are the TeX the stub received, as `\\detokenize` shows it: a space follows each control word and
runs of spaces are one, so both tiers agree byte for byte.
"""

import dataclasses
import typing
from collections.abc import Mapping, Sequence

from ._internal.read import (
    detokenized as detokenized,
    read_field,
)
from ._internal.render import Arg, argument_text, newcommand_fits, signature, tex_arguments, xparse_spec
from .body import HOLE, Comment, Cs, Group, Hole, Library, Lit, Ref, RefKind, Seq, TexRaw
from .components import Command, Environment, Node, Passthrough, Resolved, control_name
from .errors import DeclarationError, Violation
from .plan import FieldEdit
from .types import Raw, escape

type Component = type[Command] | type[Environment]

if typing.TYPE_CHECKING:
    from .package import Package

_COUNTER = r"\tmstubcalls"
_HEADS = {RefKind.CALL: "", RefKind.OPEN: "begin:", RefKind.CLOSE: "end:"}


def _groups(text: str) -> list[str]:
    """The top-level `{...}` groups of `text`; a backslash escapes the next character."""
    out: list[str] = []
    depth, start, i = 0, 0, 0
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 1
        elif c == "{":
            depth += 1
            start = i + 1 if depth == 1 else start
        elif c == "}":
            depth -= 1
            if depth == 0:
                out.append(text[start:i])
        i += 1
    return out


@dataclasses.dataclass(frozen=True)
class Call:
    """A stubbed component called: its control sequence name (`cdFact`, no backslash), its arguments in TeX order (the
    optional one first, empty when left out) as `\\detokenize` shows them, and whether it is a command call or the
    start or end of an environment."""

    name: str
    args: tuple[str, ...] = ()
    kind: RefKind = RefKind.CALL

    def probe_value(self) -> str:
        """What the TeX stub writes after `texmodel:probe:callN=`: `cdFact{a}{b}`, `begin:cdBox{a}`, `end:cdBox`."""
        return _HEADS[self.kind] + self.name + "".join(f"{{{a}}}" for a in self.args)

    @classmethod
    def parse(cls, value: str) -> "Call":
        """The `Call` a probe value stands for; braces inside an argument are balanced or backslash-escaped."""
        kind = next((k for k, head in _HEADS.items() if head and value.startswith(head)), RefKind.CALL)
        name, brace, rest = value.removeprefix(_HEADS[kind]).partition("{")
        return cls(name, tuple(_groups(brace + rest)), kind)


def read_call(cls: Component, call: Call) -> tuple[FieldEdit, ...]:
    """Each argument of `call` as a `FieldEdit`: its field, its text and the typed value that text reads back to. An
    optional argument left out or empty has no value. A text that is not a value of the field's type has a
    `Violation` (`TM-C021`) whose path is the field; what the text cannot say (a colour's model, a key list) has
    neither value nor violation. A closing call has no arguments."""
    if call.kind is RefKind.CLOSE:
        return ()
    return tuple(read_field(a, text) for a, text in zip(tex_arguments(_args(cls)), call.args, strict=True))


def _text(a: Arg, value: object) -> str:
    """What `#name` stands for in a body for this argument value: nothing for an unset one, and for a token what xparse
    gives (`\\BooleanTrue`, `\\BooleanFalse`)."""
    if a.token:
        return r"\BooleanTrue" if value else r"\BooleanFalse"
    return "" if value is None else argument_text(a, value)


def _args(cls: type) -> tuple[Arg, ...]:
    return typing.cast("tuple[Arg, ...]", getattr(cls, "__tm_args__"))  # noqa: B009


def _control(cls: type) -> str:
    """The control sequence name of a registered component, or a refusal to stub what no package registered."""
    if not hasattr(cls, "__tm_cs__"):
        raise DeclarationError(
            f"{cls.__name__}: not registered with a package, so it cannot be stubbed",
            code="TM-M019",
            path=cls.__name__,
            hint="stub a class decorated with its package's command / environment",
        )
    return control_name(cls)


def _call(cls: type, values: Mapping[str, str], kind: RefKind) -> Call:
    shown = () if kind is RefKind.CLOSE else tuple(detokenized(values[a.name]) for a in tex_arguments(_args(cls)))
    return Call(_control(cls), shown, kind)


class _Out:
    """The result under construction: text accumulates until a call splits it."""

    def __init__(self) -> None:
        self.items: list[Call | str] = []
        self.text = ""

    def write(self, text: str) -> None:
        self.text += text

    def call(self, call: Call) -> None:
        self.flush()
        self.items.append(call)

    def flush(self) -> None:
        if self.text:
            self.items.append(self.text)
            self.text = ""


def _inline(piece: object, values: Mapping[str, str], stubs: frozenset[type], out: _Out) -> None:
    if isinstance(piece, Ref):
        _ref(piece, values, stubs, out)
    elif isinstance(piece, Lit):
        out.write(escape(piece.text))
    elif isinstance(piece, Raw):
        out.write(piece.tex)
    elif isinstance(piece, Hole):
        out.write(values[piece.name])
    elif isinstance(piece, Cs):
        out.write(f"\\{piece.name}")
    elif isinstance(piece, Group | Seq):
        braces = isinstance(piece, Group)
        out.write("{" if braces else "")
        for inner in typing.cast("tuple[object, ...]", piece.pieces):
            _inline(inner, values, stubs, out)
        out.write("}" if braces else "")


def _pieces(pieces: Sequence[Resolved], values: Mapping[str, str], stubs: frozenset[type], out: _Out) -> None:
    """One line per piece, as `join` writes them; a comment is no text."""
    for piece in pieces:
        if isinstance(piece, Comment):
            continue
        if isinstance(piece, TexRaw):
            out.write(HOLE.sub(lambda m: "#" if m[0] == "##" else values[m["name"]], piece.body))
        else:
            _inline(piece, values, stubs, out)
        out.write("\n")


def _body(cls: type, which: int | None, values: Mapping[str, str], stubs: frozenset[type], out: _Out) -> None:
    """The body of a registered component (`which` 0 or 1 for an environment's begin and end); an adopted component
    has none, so it adds nothing."""
    source = getattr(cls, "__tm_inline__")  # noqa: B009
    found = source if which is None else source[which]
    if found is not None:
        _pieces(found[0], values, stubs, out)


def _ref(ref: Ref, values: Mapping[str, str], stubs: frozenset[type], out: _Out) -> None:
    mine = {
        a.name: values[v.name] if isinstance(v, Hole) else _text(a, v)
        for a, v in zip(_args(ref.target), ref.values, strict=True)
    }
    if ref.target in stubs:
        out.call(_call(ref.target, mine, ref.kind))
    else:
        _body(ref.target, None if ref.kind is RefKind.CALL else int(ref.kind is RefKind.CLOSE), mine, stubs, out)


def _walk(node: Node, stubs: frozenset[type], out: _Out) -> None:
    if isinstance(node, Comment):
        return
    if isinstance(node, Passthrough):
        out.write(node.tex.tex + "\n")
        return
    cls = type(node)
    values = {a.name: _text(a, getattr(node, a.name)) for a in _args(cls)}
    if isinstance(node, Command):
        if cls in stubs:
            out.call(_call(cls, values, RefKind.CALL))
        else:
            _body(cls, None, values, stubs, out)
        return
    stubbed = cls in stubs
    out.call(_call(cls, values, RefKind.OPEN)) if stubbed else _body(cls, 0, values, stubs, out)
    for child in node.content:
        _walk(child, stubs, out)
    out.call(_call(cls, values, RefKind.CLOSE)) if stubbed else _body(cls, 1, values, stubs, out)


def expand(node: Node, stubs: Sequence[Component] = ()) -> list[Call | str]:
    """What `node` makes TeX do, without TeX: its body text and the `Call` of every stubbed component, in order.

    A non-stubbed component is walked into through its body, with the arguments it was called with; a stubbed one
    (a class registered with a package) becomes a `Call` and its body is not read. Children of an environment are
    walked in order. Deterministic and pure."""
    for cls in stubs:
        _control(cls)  # refuses a class no package registered
    out = _Out()
    _walk(node, frozenset(stubs), out)
    out.flush()
    return out.items


def _probe(head: str, tail: str) -> str:
    return rf"\global\advance{_COUNTER} by 1 \typeout{{texmodel:probe:call\the{_COUNTER}={head}{tail}}}"


def stub_tex(stubs: Sequence[Component]) -> str:
    """The TeX that replaces each stub by a macro writing `texmodel:probe:callN=<Call.probe_value()>`, N counting every
    call in the document, so the log keeps their order. Meant for `PreambleSlots.after_package`."""
    lines = [rf"\newcount{_COUNTER}", r"\AtEndDocument{\null}"]  # the document needs a page to be compiled
    for cls in stubs:
        name, args = _control(cls), _args(cls)
        shown = "".join(f"{{#{i}}}" for i in range(1, len(args) + 1))
        arg_part = rf"\detokenize{{{shown}}}" if shown else ""
        fits = newcommand_fits(args)
        parameters = signature(args) if fits else f"{{{xparse_spec(args)}}}"
        if issubclass(cls, Environment):
            definer = r"\renewenvironment" if fits else r"\RenewDocumentEnvironment"
            lines.append(rf"\providecommand{{\{name}}}{{}}\providecommand{{\end{name}}}{{}}")
            lines.append(
                rf"{definer}{{{name}}}{parameters}{{{_probe(f'begin:{name}', arg_part)}}}"
                rf"{{{_probe(f'end:{name}', '')}}}"
            )
        else:
            definer = r"\renewcommand" if fits else r"\RenewDocumentCommand"
            lines.append(rf"\providecommand{{\{name}}}{{}}")
            lines.append(rf"{definer}{{\{name}}}{parameters}{{{_probe(name, arg_part)}}}")
    return "\n".join(lines)


def _defined(package: "Package") -> list[tuple[Component, Library]]:
    """The registered components a library block defines, with the block."""
    return [
        (c, c.defined_by)
        for c in package.registered
        if issubclass(c, Command | Environment) and c.defined_by is not None
    ]


_EXPORT = (
    r"\newcommand\tmexport[1]{\ifcsname #1\endcsname\typeout{texmodel:probe:def.#1=yes}"
    r"\edef\tmexportmeaning{\expandafter\meaning\csname #1\endcsname}"
    r'\directlua{local m=[==[\tmexportmeaning]==]; local _,e=m:find("macro:",1,true); local n="?"; '
    r'if e then local t=m:find("->",e,true); local _,k=m:sub(e+1,t-1):gsub(string.char(35),""); n=k end; '
    r'texio.write_nl("texmodel:probe:arity.#1="..n)}'
    r"\else\typeout{texmodel:probe:def.#1=no}\fi}"
)


def export_probes(package: "Package") -> str:
    """TeX for `PreambleSlots.after_package` that writes, per component a library block defines,
    `texmodel:probe:def.<cs>` (`yes` or `no`) and `texmodel:probe:arity.<cs>` (the `#` parameters of its
    `\\meaning`, `?` when that is not a macro's), for `check_exports` (§21). Needs LuaTeX."""
    calls = [rf"\tmexport{{{control_name(c)}}}" for c, _ in _defined(package)]
    return "\n".join([_EXPORT, *calls]) if calls else ""


def check_exports(package: "Package", probes: Mapping[str, str]) -> list[Violation]:
    """The components a library block defines against what the compile found (`TM-C010` not defined, `TM-C011` another
    number of arguments: an optional first one counts, and `?` checks existence only). `probes` are the `name=value`
    pairs of the `texmodel:probe:` lines."""
    out: list[Violation] = []
    for cls, lib in _defined(package):
        control, want = control_name(cls), str(len(cls.__tm_args__))
        got = probes.get(f"arity.{control}", "?")
        if probes.get(f"def.{control}") != "yes":
            message = f"\\{control} is declared as defined by library {lib.name}, but the compile does not define it"
            out.append(Violation("TM-C010", cls.__name__, message))
        elif got not in ("?", want):
            message = f"\\{control}: declared {want} argument(s), the compile defines {got}"
            out.append(Violation("TM-C011", cls.__name__, message, hint="change the declaration or the block"))
    return out


__all__ = ["Call", "Component", "check_exports", "detokenized", "expand", "export_probes", "read_call", "stub_tex"]
