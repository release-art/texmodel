"""TeX as tokens, not lines: a tokenizer with source spans and a reader of the declarations in it.

This is not an interpreter (N1): there is no expansion, no `\\catcode` beyond the switches below, and a name defined
another way is not found. What it does know, and a regex does not: comments eat their line end, `\\verb` and verbatim
environments are text, `@` is a letter between `\\makeatletter` and `\\makeatother` and `_` and `:` between
`\\ExplSyntaxOn` and `\\ExplSyntaxOff`, a group is balanced, and `\\iffalse ... \\fi` is dead.
"""

import dataclasses
import enum
import re
from collections.abc import Sequence


@enum.unique
class Kind(enum.Enum):
    WORD = "word"  # `\name`
    SYMBOL = "symbol"  # `\&`, `\ `
    OPEN = "open"
    CLOSE = "close"
    PARAM = "param"  # `#`
    CHAR = "char"  # any other character, one at a time
    SPACE = "space"
    PAR = "par"  # a blank line
    COMMENT = "comment"  # `%` to the line end and the next line's indent, which TeX drops
    VERBATIM = "verbatim"  # the text of `\verb|...|` or of a verbatim environment, never read as TeX


@dataclasses.dataclass(frozen=True, slots=True)
class Token:
    kind: Kind
    start: int
    end: int
    text: str

    @property
    def name(self) -> str:
        """A control word's name, without the backslash."""
        return self.text[1:]


TEX_SPACE = " \t\r\n"  # LuaTeX: any other character, a no-break space and a form feed included, is not a space
_BLANK = frozenset({Kind.SPACE, Kind.PAR, Kind.COMMENT})
_BLANKS = re.compile(r"[ \t\r]+")
_LINE_END = re.compile(r"[ \t\r]*\n[ \t\r]*")  # the end of a line, and the next line's indent, which TeX drops
_VERBATIM_BEGIN = re.compile(r"\s*\{(verbatim\*?|Verbatim\*?|lstlisting|comment)\}")


class _Lexer:
    """One pass over the text; the category codes it reads with change at the switches in `_after_word`."""

    def __init__(self, text: str, at_letter: bool, expl3: bool) -> None:
        self.text = text
        self.at_letter = at_letter
        self.expl3 = expl3
        self.i = 0
        self.out: list[Token] = []
        self.fresh = True  # at the start of a line, where a line end is an empty line
        self.scopes: list[tuple[bool, bool]] = []  # the category codes outside each open group, which it restores

    def emit(self, kind: Kind, end: int) -> None:
        self.out.append(Token(kind, self.i, end, self.text[self.i : end]))
        if kind in {Kind.COMMENT, Kind.SPACE, Kind.PAR} and "\n" in self.out[-1].text:
            self.fresh = True
        elif kind is not Kind.SPACE:
            self.fresh = False
        self.i = end

    def letter(self, c: str) -> bool:
        return (
            c.isalpha() or (self.at_letter and c == "@") or (self.expl3 and c in "_:")
        )  # LuaTeX: Unicode letters are letters

    def run(self) -> list[Token]:
        while self.i < len(self.text):
            c = self.text[self.i]
            if c == "\\":
                self.control()
            elif c == "%":
                self.comment()
            elif c == "{":
                self.push()
                self.emit(Kind.OPEN, self.i + 1)
            elif c == "}":
                self.pop()
                self.emit(Kind.CLOSE, self.i + 1)
            elif c in TEX_SPACE:
                self.space()
            else:
                self.emit(Kind.PARAM if c == "#" else Kind.CHAR, self.i + 1)
        return self.out

    def push(self) -> None:
        self.scopes.append((self.at_letter, self.expl3))

    def pop(self) -> None:
        if self.scopes:
            self.at_letter, self.expl3 = self.scopes.pop()

    def space(self) -> None:
        """Blanks and line ends: the first line end after text is a space, an empty line (a line end that starts a
        line, as after a comment) is a paragraph, one `\\par` per empty line."""
        if end := _LINE_END.match(self.text, self.i):
            self.emit(Kind.PAR if self.fresh else Kind.SPACE, end.end())
        else:
            blanks = _BLANKS.match(self.text, self.i)
            assert blanks  # c is whitespace
            self.emit(Kind.SPACE, blanks.end())

    def comment(self) -> None:
        eol = self.text.find("\n", self.i)
        j = len(self.text) if eol == -1 else eol + 1
        while j < len(self.text) and self.text[j] in " \t":
            j += 1
        self.emit(Kind.COMMENT, j)

    def control(self) -> None:
        text, j = self.text, self.i + 1
        if j >= len(text) or not self.letter(text[j]):
            self.emit(Kind.SYMBOL, min(self.i + 2, len(text)))
            return
        while j < len(text) and self.letter(text[j]):
            j += 1
        self.emit(Kind.WORD, j)
        match self.out[-1].name:
            case "makeatletter" | "makeatother":
                self.at_letter = self.out[-1].name == "makeatletter"
            case "ExplSyntaxOn" | "ExplSyntaxOff":
                self.expl3 = self.out[-1].name == "ExplSyntaxOn"
            case "verb":
                self.verb()
            case "begin":
                self.push()  # an environment is a group: a `\\makeatother` in it ends with it
                self.verbatim_environment()
            case "begingroup" | "bgroup":
                self.push()
            case "end" | "endgroup" | "egroup":
                self.pop()
            case _:
                pass

    def verb(self) -> None:
        """`\\verb*|text|`: the text runs to the next delimiter, or to the line end."""
        text, k = self.text, self.i + (self.text[self.i : self.i + 1] == "*")
        if k < len(text) and text[k] not in TEX_SPACE:
            close, eol = text.find(text[k], k + 1), text.find("\n", k + 1)
            stop = close + 1 if close != -1 and (eol == -1 or close < eol) else (len(text) if eol == -1 else eol)
            self.emit(Kind.VERBATIM, stop)

    def verbatim_environment(self) -> None:
        """`\\begin{verbatim}`: the group, then the text up to its `\\end` (or to the end of the text)."""
        if not (m := _VERBATIM_BEGIN.match(self.text, self.i)):
            return
        brace = self.text.index("{", self.i)
        if brace > self.i:
            self.emit(Kind.SPACE, brace)
        self.emit(Kind.OPEN, brace + 1)
        self.emit(Kind.CHAR, m.end() - 1)
        self.emit(Kind.CLOSE, m.end())
        stop = self.text.find(f"\\end{{{m[1]}}}", self.i)
        if (stop := len(self.text) if stop == -1 else stop) > self.i:
            self.emit(Kind.VERBATIM, stop)


def tokenize(text: str, *, at_letter: bool = True, expl3: bool = False) -> list[Token]:
    """`text` as tokens that cover it, in order. `at_letter` and `expl3` are the starting category codes: a `.sty` is
    read with `@` a letter, a `.tex` document without."""
    return _Lexer(text, at_letter, expl3).run()


def detokenize(toks: Sequence[Token]) -> str:
    """The tokens of a macro argument as `\\detokenize` shows them: a space after a control word, which swallows the
    spaces after it (so does a paragraph), a run of spaces one, a blank line `\\par`, a `#` doubled, a comment gone."""
    out: list[str] = []
    skipping = False
    for t in toks:
        if t.kind is Kind.COMMENT:
            continue
        if t.kind is Kind.SPACE:
            if not skipping:
                out.append(" ")
            skipping = True
            continue
        out.append({Kind.PAR: "\\par ", Kind.PARAM: "##", Kind.WORD: f"{t.text} "}.get(t.kind, t.text))
        skipping = t.kind in {Kind.PAR, Kind.WORD} or t.text == "\\ "
    return "".join(out)


def detokenized(tex: str) -> str:
    """`tex` as `\\detokenize` shows a macro argument (`detokenize`), leading spaces gone."""
    return detokenize(tokenize("x" + tex, at_letter=False)[1:]).lstrip(TEX_SPACE)  # "x": the text starts mid-line


def call_text(text: str, name: str) -> tuple[str | None, str] | None:
    """`\\name[optional]{required}` and nothing else: the text of the optional argument (None when left out) and of
    the required one; None for any other text."""
    toks = [t for t in tokenize(text) if t.kind not in _BLANK]
    if not toks or toks[0].kind is not Kind.WORD or toks[0].name != name:
        return None
    after = _after_brackets(toks, 1)
    optional = text[toks[1].end : toks[after - 1].start] if after > 1 else None
    named = _group(toks, after)
    if named is None or named[1] != len(toks):
        return None
    inner = named[0]
    return optional, text[inner[0].start : inner[-1].end] if inner else ""


def control_words(text: str) -> list[str]:
    """The names of the control words in `text` that run, in order: not in a comment or a verbatim, nor written out
    with `\\string` or `\\noexpand`."""
    out: list[str] = []
    before: Token | None = None
    for t in tokenize(text):
        if t.kind is Kind.WORD and not (before and before.kind is Kind.WORD and before.name in _LITERAL):
            out.append(t.name)
        if t.kind not in _BLANK:
            before = t
    return out


def count_outside_groups(text: str, c: str) -> int:
    """How many times the character `c` stands in `text` outside every `{...}`."""
    depth = count = 0
    for t in tokenize(text):
        depth += t.kind is Kind.OPEN
        depth -= t.kind is Kind.CLOSE
        count += depth == 0 and t.kind is Kind.CHAR and t.text == c
    return count


def is_balanced(text: str) -> bool:
    """Every `{` closes and no `}` comes first; an escaped brace, a comment and a verbatim hold none."""
    depth = 0
    for t in tokenize(text):
        depth += t.kind is Kind.OPEN
        depth -= t.kind is Kind.CLOSE
        if depth < 0:
            return False
    return depth == 0


# --- declarations ---------------------------------------------------------------------------------------------


@enum.unique
class Form(enum.Enum):
    """The way a name is declared: what its signature means and which definers write it."""

    COMMAND = "command"  # `\newcommand`, `\providecommand`, `\DeclareRobustCommand`, `\def`: `[n]` or `[n][]`
    ENVIRONMENT = "environment"  # `\newenvironment`
    XPARSE = "xparse"  # `\NewDocumentCommand` and `\NewDocumentEnvironment`: the argument types as letters
    REGISTER = "register"  # `\newlength`, `\newsavebox`, `\newfontfamily`, `\newtoggle`, `\newif`: no arguments
    FUNCTION = "function"  # expl3's `\cs_new:Npn`, `\cs_new:Nn`: `[n]` from the argument specification in the name
    COLOUR = "colour"
    COUNTER = "counter"
    REDEFINED = (
        "redefined"  # `\renewcommand`, `\renewenvironment`, `\RenewDocumentCommand` and kin: a name, no signature
    )
    LOAD = "load"  # `\\RequirePackage[opts]{a,b}` and kin: the name is the names as written, the signature the command


@dataclasses.dataclass(frozen=True, slots=True)
class Declaration:
    form: Form
    name: str  # without the backslash
    signature: str  # "" for none; `?` where the definition is not readable
    start: int  # where the definer is, and where the declaration ends: for a diagnostic
    end: int


_COMMANDS = frozenset({"newcommand", "providecommand", "DeclareRobustCommand"})
PRIMITIVE_DEFS = frozenset({"def", "gdef", "edef", "xdef"})
XPARSE_COMMANDS = frozenset(
    f"{v}{e}DocumentCommand" for v in ("New", "Renew", "Provide", "Declare") for e in ("", "Expandable")
)
XPARSE_ENVIRONMENTS = frozenset(f"{v}DocumentEnvironment" for v in ("New", "Renew", "Provide", "Declare"))
_RENEWED_COMMANDS = frozenset({"renewcommand", *(w for w in XPARSE_COMMANDS if w.startswith("Renew"))})
_RENEWALS = _RENEWED_COMMANDS | {"renewenvironment", "RenewDocumentEnvironment"}
_REGISTERS = frozenset({"newlength", "newsavebox", "newfontfamily"})
_COLOURS = frozenset({"definecolor", "colorlet", "providecolor"})
_FUNCTIONS = frozenset(
    f"cs_new{p}:{a}" for p in ("", "_protected", "_nopar", "_protected_nopar") for a in ("Npn", "Nn")
)
_LOADERS = frozenset(
    {"RequirePackage", "RequirePackageWithOptions", "usepackage", "LoadClass", "LoadClassWithOptions", "tcbuselibrary"}
)
_LITERAL = frozenset({"string", "noexpand"})  # `\string\newcommand` writes the word out and defines nothing
_CONDITIONALS = frozenset(
    "if ifx ifnum ifdim ifodd ifvmode ifhmode ifmmode ifinner ifcat ifcase ifdefined ifcsname iffontchar ifvoid ifhbox "
    "ifvbox ifeof iftrue iffalse".split()
)


def _group(toks: Sequence[Token], i: int) -> tuple[Sequence[Token], int] | None:
    """The tokens inside the balanced `{...}` at `i` and the index after it; None if there is none or it never ends."""
    if i >= len(toks) or toks[i].kind is not Kind.OPEN:
        return None
    depth = 0
    for j in range(i, len(toks)):
        depth += toks[j].kind is Kind.OPEN
        depth -= toks[j].kind is Kind.CLOSE
        if depth == 0:
            return toks[i + 1 : j], j + 1
    return None


def _control(toks: Sequence[Token], i: int) -> tuple[str, int] | None:
    """The name of the control word at `i`, bare or in braces (`\\x`, `{\\x}`), and the index after it. `\\csname`
    names nothing: the name is only known once it expands."""
    if i < len(toks) and toks[i].kind is Kind.WORD:
        found: tuple[Sequence[Token], int] | None = toks[i : i + 1], i + 1
    else:
        found = _group(toks, i)
    if found and len(found[0]) == 1 and found[0][0].kind is Kind.WORD and found[0][0].name != "csname":
        return found[0][0].name, found[1]
    return None


def _plain(text: str, toks: Sequence[Token], i: int) -> tuple[str, int] | None:
    """The text of the `{name}` at `i` (inner spaces kept, ends trimmed), if it holds no control sequence."""
    found = _group(toks, i)
    if not found or not found[0] or any(t.kind in {Kind.WORD, Kind.SYMBOL, Kind.PARAM} for t in found[0]):
        return None
    name = text[found[0][0].start : found[0][-1].end].strip()
    return (name, found[1]) if name else None


def _after_brackets(toks: Sequence[Token], i: int) -> int:
    """The index after the `[...]` at `i` (its `]` outside braces), or `i` if there is none or it never closes."""
    if not _char(toks, i, "["):
        return i
    depth = 0
    for j in range(i + 1, len(toks)):
        depth += toks[j].kind is Kind.OPEN
        depth -= toks[j].kind is Kind.CLOSE
        if depth == 0 and _char(toks, j, "]"):
            return j + 1
    return i


def _char(toks: Sequence[Token], i: int, c: str) -> bool:
    return i < len(toks) and toks[i].kind is Kind.CHAR and toks[i].text == c


def _count_signature(toks: Sequence[Token], i: int) -> str:
    """`[n]` and `[n][]` after a `\\newcommand` name: an argument count, then a default for the first."""
    if not (_char(toks, i, "[") and i + 2 < len(toks) and toks[i + 1].text.isdigit() and _char(toks, i + 2, "]")):
        return ""
    return f"[{toks[i + 1].text}]" + ("[]" if _char(toks, i + 3, "[") else "")


def _parameter_signature(toks: Sequence[Token], i: int) -> str:
    """`[n]` for the `#1#2` before a `\\def`'s body; `?` for a delimited parameter text (not an argument count)."""
    n = 0
    while i < len(toks) and toks[i].kind is not Kind.OPEN:
        if toks[i].kind is Kind.PARAM and i + 1 < len(toks) and toks[i + 1].text.isdigit():
            n += 1
            i += 2
        else:
            return "?"
    return "?" if i >= len(toks) else (f"[{n}]" if n else "")


def _body_end(toks: Sequence[Token], i: int, groups: int = 1) -> int:
    """The index after the `groups` braced bodies of a definition whose name ends at `i` (its `[n][d]` or parameter text
    in between); `i` if it has none. A definer inside a body runs when the macro does, not when the text loads."""
    j = _after_brackets(toks, _after_brackets(toks, i))
    while j < len(toks) and toks[j].kind is not Kind.OPEN:
        j += 1
    for _ in range(groups):
        if (found := _group(toks, j)) is None:
            return i
        j = found[1]
    return j


def _skip_group(toks: Sequence[Token], i: int) -> int:
    """The index after the `{...}` at `i`, or `i` when there is none (a default left out)."""
    return named[1] if (named := _group(toks, i)) else i


def _grouped_type(text: str, toks: Sequence[Token], i: int, c: str) -> tuple[str, int] | None:
    """The letters and next index of `u{delimiters}`, `e{embellishments}` and `E{embellishments}{defaults}` (one default
    for each embellishment) whose group starts at `i`; None without the group."""
    if (named := _group(toks, i)) is None:
        return None
    j = named[1]
    for _ in named[0] if c == "E" else ():
        j = _skip_group(toks, j)
    return c.lower() + text[toks[i].start : toks[named[1] - 1].end], j


def _xparse_letters(text: str, toks: Sequence[Token]) -> str:
    """The letters of an xparse argument specification, read from its tokens (no blanks)."""
    out: list[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        i += 1
        c = t.text if t.kind is Kind.CHAR else ""
        if c in {"m", "o", "s", "v", "g"}:
            out.append(c)
        elif c in {"O", "G"}:
            out.append(c.lower())
            i = _skip_group(toks, i)
        elif c in {"d", "D", "r", "R"} and i + 1 < len(toks):
            out.append(f"{c.lower()}{toks[i].text}{toks[i + 1].text}")
            i = _skip_group(toks, i + 2) if c in {"D", "R"} else i + 2
        elif c == "t" and i < len(toks):
            out.append(f"t{toks[i].text}")
            i += 1
        elif c in {"u", "e", "E"} and (grouped := _grouped_type(text, toks, i, c)):
            out.append(grouped[0])
            i = grouped[1]
        elif c != "+":
            return "?"
    return "".join(out)


def xparse_letters(spec: str) -> str:
    """`O{}mm` as `omm`; `d()` and `t*` keep their characters, `u{.}` and `e{^_}` their group; a type that is not
    one of xparse's gives `?`."""
    return _xparse_letters(spec, [t for t in tokenize(spec) if t.kind not in _BLANK])


def _before(toks: Sequence[Token], j: int) -> int:
    """The index of the token before `j` that is not a space, a paragraph or a comment; -1 if there is none."""
    j -= 1
    while j >= 0 and toks[j].kind in _BLANK:
        j -= 1
    return j


def _let_value(toks: Sequence[Token], j: int) -> bool:
    """The token `j` is what `\\let\\x` or `\\let\\x=` copies (`\\let\\ifa\\iffalse`): not a test."""
    k = _before(toks, j)
    if k >= 0 and toks[k].kind is Kind.CHAR and toks[k].text == "=":
        k = _before(toks, k)
    k = _before(toks, k) if k >= 0 else k  # the control sequence being defined
    return k >= 0 and toks[k].kind is Kind.WORD and toks[k].name == "let"


def dead_end(toks: Sequence[Token], i: int, flags: frozenset[str]) -> int:
    """After `\\iffalse` at `i - 1`: the index where text is live again, past the `\\fi` or `\\else` ending it. An
    `\\iffalse` that a `\\let` copies or a list names is no test, and text goes on at `i`."""
    if _let_value(toks, i - 1) or i < len(toks) and toks[i].text == ",":  # `\\DoNotIndex{\\iffalse,\\fi}`
        return i
    depth = 0
    for j in range(i, len(toks)):
        if toks[j].kind is not Kind.WORD:
            continue
        name = toks[j].name
        if name in _CONDITIONALS or name.startswith("if@") or name in flags:
            depth += not _let_value(toks, j)
        elif name == "fi" and depth == 0 or name == "else" and depth == 0:
            return j + 1
        elif name == "fi":
            depth -= 1
    return len(toks)


class _Reader:
    """Walks the tokens that typeset (no space, paragraph or comment) and collects what its definers declare."""

    def __init__(self, text: str, expl3: bool) -> None:
        self.text = text
        self.toks = [t for t in tokenize(text, expl3=expl3) if t.kind not in _BLANK]
        self.found: list[Declaration] = []
        self.flags: set[str] = set()  # the `\newif` conditionals seen: each ends in `\fi`
        self.i = 0

    def read(self) -> list[Declaration]:
        while self.i < len(self.toks):
            t = self.toks[self.i]
            self.i += 1
            if t.kind is Kind.WORD and not self.literal():
                self.definer(t)
        return self.found

    def literal(self) -> bool:
        """The word just read follows `\\string` or `\\noexpand`: it is written out, not run."""
        before = self.toks[self.i - 2] if self.i > 1 else None
        return before is not None and before.kind is Kind.WORD and before.name in _LITERAL

    def add(self, form: Form, name: str, signature: str, definer: Token, end: int) -> None:
        self.found.append(
            Declaration(form, name, signature, definer.start, self.toks[min(end, len(self.toks)) - 1].end)
        )

    def definer(self, t: Token) -> None:
        word = t.name
        if word == "iffalse":
            self.i = dead_end(self.toks, self.i, frozenset(self.flags))
        elif word in _COMMANDS or word in PRIMITIVE_DEFS:
            self.command(t)
        elif word == "newenvironment":
            self.environment(t)
        elif word in _RENEWALS:
            self.renewal(t)
        elif word in XPARSE_COMMANDS or word in XPARSE_ENVIRONMENTS:
            self.xparse(t)
        elif word in _REGISTERS or word in {"newtoggle", "newif"}:
            self.register(t)
        elif word in _COLOURS or word == "newcounter":
            self.named(t)
        elif word in _FUNCTIONS:
            self.function(t)
        elif word in _LOADERS:
            self.load(t)

    def command(self, t: Token) -> None:
        toks, word = self.toks, t.name
        if word in _COMMANDS:
            self.i += _char(toks, self.i, "*")
        if named := _control(toks, self.i):
            signature = _count_signature(toks, named[1]) if word in _COMMANDS else _parameter_signature(toks, named[1])
            self.add(Form.COMMAND, named[0], signature, t, named[1])
            self.i = _body_end(toks, named[1])

    def environment(self, t: Token) -> None:
        self.i += _char(self.toks, self.i, "*")
        if named := _plain(self.text, self.toks, self.i):
            self.add(Form.ENVIRONMENT, named[0], _count_signature(self.toks, named[1]), t, named[1])
            self.i = _body_end(self.toks, named[1], 2)

    def renewal(self, t: Token) -> None:
        """A renewal declares nothing, whatever its definer: the name is the package's."""
        self.i += _char(self.toks, self.i, "*")
        named = _control(self.toks, self.i) if t.name in _RENEWED_COMMANDS else _plain(self.text, self.toks, self.i)
        if named:
            self.add(Form.REDEFINED, named[0], "", t, named[1])

    def xparse(self, t: Token) -> None:
        toks = self.toks
        named = _control(toks, self.i) if t.name in XPARSE_COMMANDS else _plain(self.text, toks, self.i)
        if not named:
            return
        if spec := _group(toks, named[1]):
            inner = spec[0]
            letters = _xparse_letters(self.text, inner) if inner else ""
            self.add(Form.XPARSE, named[0], letters, t, spec[1])
            self.i = _body_end(toks, spec[1], 1 if t.name in XPARSE_COMMANDS else 2)
        else:
            self.add(Form.XPARSE, named[0], "?", t, named[1])

    def register(self, t: Token) -> None:
        toks, word = self.toks, t.name
        if word == "newif":
            if self.i < len(toks) and toks[self.i].kind is Kind.WORD and toks[self.i].name.startswith("if"):
                self.flags.add(toks[self.i].name)
                flag = toks[self.i].name.removeprefix("if")
                for name in (f"if{flag}", f"{flag}true", f"{flag}false"):
                    self.add(Form.REGISTER, name, "", t, self.i + 1)
            return
        named = _plain(self.text, toks, self.i) if word == "newtoggle" else _control(toks, self.i)
        if named:
            self.add(Form.REGISTER, named[0], "", t, named[1])

    def named(self, t: Token) -> None:
        """A colour or a counter: `{name}`, which is not a control sequence."""
        if named := _plain(self.text, self.toks, self.i):
            self.add(Form.COUNTER if t.name == "newcounter" else Form.COLOUR, named[0], "", t, named[1])

    def load(self, t: Token) -> None:
        """`\\usepackage[opts]{names}`: the names as written; no group (`\\usepackage\\x`) names nothing."""
        i = _after_brackets(self.toks, self.i)
        if (named := _group(self.toks, i)) is not None:
            inner, end = named
            self.add(Form.LOAD, self.text[inner[0].start : inner[-1].end] if inner else "", t.name, t, end)

    def function(self, t: Token) -> None:
        """expl3's `\\cs_new:Npn \\name:nn`: the argument count is the specification after the colon."""
        if self.i < len(self.toks) and self.toks[self.i].kind is Kind.WORD and ":" in self.toks[self.i].text:
            name = self.toks[self.i].name
            n = sum(c in "NncVvofxeTF" for c in name.partition(":")[2])
            self.add(Form.FUNCTION, name, f"[{n}]" if n else "", t, self.i + 1)
            self.i = _body_end(self.toks, self.i + 1)


def declarations(text: str, *, expl3: bool = False) -> list[Declaration]:
    """What `text` declares, in source order, by the forms in `Form`. A form not listed there is not read, so a name
    defined that way is missing, not guessed at. Text that does not typeset (a comment, a verbatim, an `\\iffalse`) and
    a definer written out with `\\string` declare nothing. `expl3` starts the text in expl3 syntax (a library block
    that texmodel wraps in `\\ExplSyntaxOn`)."""
    return _Reader(text, expl3).read()
