"""The calls of known components in a document, read from its tokens (no TeX run).

A stub compile (`texmodel.testing.stub_tex`) logs the calls TeX makes; this reads the calls the text writes, by the
signature each component declares: a required argument is a group or one token, an optional one is read only when its
opening delimiter comes next (spaces before it are skipped, as TeX does), a token slot (`*`) is `\\BooleanTrue` or
`\\BooleanFalse`. The arguments are shown as `\\detokenize` shows them, so a `Call` equals the stub's.

It reads what is written, not what runs. A call inside a definition (`\\newcommand{\\x}{\\hdPara{a}}`) is one a
macro makes when it runs: it is `Unreadable` (`MADE_BY_MACRO`), and `\\x` is not read as a call. A component copied by
`\\let` is no call. A call TeX never reaches (`\\iffalse`, a comment, a verbatim) is not found.
"""

import dataclasses
from collections.abc import Mapping, Sequence

from ..body import RefKind
from ..components import Command, Environment
from ..testing import Call
from .read import detokenized
from .render import Arg, default_text, tex_arguments
from .tex import PRIMITIVE_DEFS, XPARSE_COMMANDS, XPARSE_ENVIRONMENTS, Kind, Token, dead_end, detokenize, tokenize

type Component = type[Command] | type[Environment]

_TRUE, _FALSE = r"\BooleanTrue ", r"\BooleanFalse "
_SKIPPED = frozenset({Kind.SPACE, Kind.COMMENT})
MADE_BY_MACRO = "a macro makes this call: it is written inside a definition"
# What follows a definer's name: whether `[n][default]` may, and how many groups (the body, and an environment's end)
_DEFINERS = (
    dict.fromkeys(("newcommand", "renewcommand", "providecommand", "DeclareRobustCommand"), (True, 1))
    | dict.fromkeys(("newenvironment", "renewenvironment"), (True, 2))
    | dict.fromkeys(XPARSE_COMMANDS, (False, 2))
    | dict.fromkeys(XPARSE_ENVIRONMENTS, (False, 3))
)


@dataclasses.dataclass(frozen=True, slots=True)
class ParsedCall:
    """A call as written: what the stub would log, where it is in the text, and where each written argument's text is
    (None for an argument left out, which has its default)."""

    call: Call
    start: int
    end: int
    spans: tuple[tuple[int, int] | None, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class Unreadable:
    """A component named where its arguments cannot be read (a missing one, a `}` or the end of the text first)."""

    name: str
    start: int
    why: str


class _Read:
    def __init__(self, text: str, classes: Mapping[str, Component]) -> None:
        self.text = text
        self.toks = tokenize(text, at_letter=False)
        self.classes = classes
        self.slots = {n: tex_arguments(c.__tm_args__) for n, c in classes.items()}
        self.i = 0
        self.out: list[ParsedCall | Unreadable] = []
        self.flags: set[str] = set()
        self.until = 0  # the calls before this token are inside a definition: a macro makes them when it runs

    def skip(self, i: int) -> int:
        while i < len(self.toks) and self.toks[i].kind in _SKIPPED:
            i += 1
        return i

    def closing(self, i: int, close: str | None) -> int | None:
        """The index of the token that ends the argument starting at `i`: the `}` of a group (`close` None) or a
        `close` character outside braces. None when the text ends or a stray `}` comes first."""
        depth = 0
        for j in range(i, len(self.toks)):
            t = self.toks[j]
            if t.kind is Kind.OPEN:
                depth += 1
            elif t.kind is Kind.CLOSE:
                if depth == 0:
                    return j if close is None else None
                depth -= 1
            elif depth == 0 and close is not None and t.kind is Kind.CHAR and t.text == close:
                return j
        return None

    def shown(self, a: int, b: int) -> str:
        """The tokens `a` up to `b` as `\\detokenize` shows an argument: one pair of braces around all of it is the
        argument's own and goes."""
        toks = self.toks[a:b]
        if toks and toks[0].kind is Kind.OPEN and self.closing(a + 1, None) == b - 1:
            toks = toks[1:-1]
        return detokenize(toks)

    def slot(self, a: Arg, i: int) -> tuple[str, tuple[int, int] | None, int] | str:
        """The text of the argument `a` at `i`, where it is, and the index after it; or why it cannot be read."""
        j = self.skip(i)
        t = self.toks[j] if j < len(self.toks) else None
        if a.token:
            if t and t.kind is Kind.CHAR and t.text == a.body.token:
                return _TRUE, (t.start, t.end), j + 1
            return _FALSE, None, i
        if a.optional or a.delimiter.open != "{":
            if t and t.kind is Kind.CHAR and t.text == a.delimiter.open:
                end = self.closing(j + 1, a.delimiter.close)
                if end is None:
                    return f"no {a.delimiter.close} closes the {a.delimiter.open} of {a.name}"
                return self.shown(j + 1, end), (self.toks[j].end, self.toks[end].start), end + 1
            if a.optional:
                return detokenized(default_text(a)), None, i
            return f"{a.name} needs its {a.delimiter.open}"
        if t is None or t.kind is Kind.CLOSE:
            return f"{a.name} is missing"
        if t.kind is Kind.OPEN:
            end = self.closing(j + 1, None)
            if end is None:
                return f"the {{ of {a.name} never closes"
            return self.shown(j, end + 1), (t.end, self.toks[end].start), end + 1
        return self.shown(j, j + 1), (t.start, t.end), j + 1

    def group_end(self, i: int) -> int | None:
        """The index after the `{...}` group at `i` (spaces and comments first), or None."""
        j = self.skip(i)
        if j >= len(self.toks) or self.toks[j].kind is not Kind.OPEN:
            return None
        end = self.closing(j + 1, None)
        return None if end is None else end + 1

    def definition_end(self, word: str, i: int) -> int:
        """The index after the definition a definer `word` ending before `i` makes: its name, parameters and bodies;
        the end of the text when it never closes."""
        if word in PRIMITIVE_DEFS:  # `\def\x#1{body}`: the parameter text, up to the first brace
            j = i
            while j < len(self.toks) and self.toks[j].kind is not Kind.OPEN:
                j += 1
            return self.group_end(j) or len(self.toks)
        brackets, groups = _DEFINERS[word]
        j = self.skip(i)
        j = self.skip(j + 1) if j < len(self.toks) and self.toks[j].text == "*" else j
        j = self.group_end(j) or j + 1  # the name: `\x` or `{\x}`
        for _ in range(2 if brackets else 0):
            j = self.skip(j)
            if j < len(self.toks) and self.toks[j].kind is Kind.CHAR and self.toks[j].text == "[":
                end = self.closing(j + 1, "]")
                j = len(self.toks) if end is None else end + 1
        for _ in range(groups):
            j = self.group_end(j) or len(self.toks)
        return j

    def call(self, name: str, kind: RefKind, start: Token, i: int) -> None:
        """The call of `name` whose name ends before `i`: its arguments, unless it is an environment's end."""
        if self.i <= self.until:
            self.out.append(Unreadable(name, start.start, MADE_BY_MACRO))
            return
        shown: list[str] = []
        spans: list[tuple[int, int] | None] = []
        end = start.end if kind is RefKind.CALL else self.toks[i - 1].end
        for a in () if kind is RefKind.CLOSE else self.slots[name]:
            got = self.slot(a, i)
            if isinstance(got, str):
                self.out.append(Unreadable(name, start.start, got))
                self.i = i
                return
            text, span, i = got
            shown.append(text)
            spans.append(span)
            end = self.toks[i - 1].end if span else end
        self.out.append(ParsedCall(Call(name, tuple(shown), kind), start.start, end, tuple(spans)))
        self.i = i

    def environment(self, t: Token, kind: RefKind) -> bool:
        """`\\begin{name}` / `\\end{name}` of a component: its call; False for anything else."""
        j = self.skip(self.i)
        if j >= len(self.toks) or self.toks[j].kind is not Kind.OPEN:
            return False
        close = self.closing(j + 1, None)
        if close is None or not all(x.kind is Kind.CHAR for x in self.toks[j + 1 : close]):
            return False
        name = self.text[self.toks[j].end : self.toks[close].start]
        if not isinstance(self.classes.get(name), type) or not issubclass(self.classes[name], Environment):
            return False
        self.call(name, kind, t, close + 1)
        return True

    def run(self) -> list[ParsedCall | Unreadable]:
        while self.i < len(self.toks):
            t = self.toks[self.i]
            self.i += 1
            if t.kind is not Kind.WORD:
                continue
            match t.name:
                case "iffalse":
                    self.i = dead_end(self.toks, self.i, frozenset(self.flags))
                case "let":  # `\let\p\hdPara` copies a component, it does not call it
                    j = self.skip(self.skip(self.i) + 1)
                    j = self.skip(j + 1) if j < len(self.toks) and self.toks[j].text == "=" else j
                    self.i = max(self.i, min(j + 1, len(self.toks)))
                case word if word in _DEFINERS or word in PRIMITIVE_DEFS:
                    self.until = max(self.until, self.definition_end(word, self.i))
                case "newif":
                    j = self.skip(self.i)
                    if j < len(self.toks) and self.toks[j].kind is Kind.WORD:
                        self.flags.add(self.toks[j].name)
                case "begin" | "end":
                    self.environment(t, RefKind.OPEN if t.name == "begin" else RefKind.CLOSE)
                case name if name in self.classes and issubclass(self.classes[name], Command):
                    self.call(name, RefKind.CALL, t, self.i)
                case _:
                    pass
        return self.out


def parse_calls(text: str, classes: Mapping[str, Component]) -> Sequence[ParsedCall | Unreadable]:
    """The calls of `classes` (control sequence name -> component) in `text`, in order, each as `Call`s read by TeX's
    own rules for arguments; a component whose arguments cannot be read is `Unreadable`."""
    return _Read(text, classes).run()
