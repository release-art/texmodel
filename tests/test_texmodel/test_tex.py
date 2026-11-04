"""The TeX tokenizer and the reader of declarations (`_internal.tex`)."""

from hypothesis import (
    given,
    strategies as st,
)

from texmodel._internal.tex import (
    Form,
    Kind,
    call_text,
    control_words,
    count_outside_groups,
    declarations,
    detokenize,
    detokenized,
    is_balanced,
    tokenize,
    xparse_letters,
)

TRICKY = st.text(alphabet="\\{}%# \n\t\r\f\u00a0@_:[]*vrbeginmakexplotrue1", max_size=60)


def kinds(text: str, **options: bool) -> list[tuple[str, str]]:
    return [(t.kind.value, t.text) for t in tokenize(text, **options) if t.kind is not Kind.SPACE]


def read(text: str) -> dict[str, str]:
    return {d.name: d.signature for d in declarations(text)}


@given(TRICKY)
def test_tokens_cover_the_text_in_order(text):
    tokens = tokenize(text)
    assert "".join(t.text for t in tokens) == text
    assert all(a.end == b.start for a, b in zip(tokens, tokens[1:], strict=False))
    declarations(text)  # nothing is an error: what is not readable is missing


def test_a_comment_takes_its_line_end_and_the_next_indent():
    assert kinds("a%x\n   b") == [("char", "a"), ("comment", "%x\n   "), ("char", "b")]
    assert kinds("a\\%b") == [("char", "a"), ("symbol", "\\%"), ("char", "b")]
    assert kinds("%end") == [("comment", "%end")]


def test_a_blank_line_is_a_paragraph_and_one_line_end_is_a_space():
    assert [t.kind for t in tokenize("a\nb\n \nc")] == [
        Kind.CHAR,
        Kind.SPACE,
        Kind.CHAR,
        Kind.SPACE,
        Kind.PAR,
        Kind.CHAR,
    ]
    assert [t.kind for t in tokenize("a%\n\nb")] == [Kind.CHAR, Kind.COMMENT, Kind.PAR, Kind.CHAR]  # after a comment


def test_letters_follow_the_category_codes_in_force():
    assert kinds(r"\a@b") == [("word", r"\a@b")]
    assert kinds(r"\a@b", at_letter=False) == [("word", r"\a"), ("char", "@"), ("char", "b")]
    assert kinds(r"\makeatother\a@b\makeatletter\a@b", at_letter=True)[1:3] == [("word", r"\a"), ("char", "@")]
    assert kinds(r"\ExplSyntaxOn\a_b:c\ExplSyntaxOff\a_b")[1] == ("word", r"\a_b:c")
    assert kinds(r"\ExplSyntaxOn\a_b:c\ExplSyntaxOff\a_b")[-2:] == [("char", "_"), ("char", "b")]
    assert kinds("\\") == [("symbol", "\\")]


def test_verb_and_verbatim_environments_are_text():
    assert kinds(r"\verb|\x{|y") == [("word", r"\verb"), ("verbatim", r"|\x{|"), ("char", "y")]
    assert kinds("\\verb*+a\nb")[1] == ("verbatim", "*+a")  # no closing delimiter on the line: to the line end
    assert kinds("\\verb") == [("word", r"\verb")]
    assert kinds("\\verb x") == [("word", r"\verb"), ("char", "x")]  # a space is no delimiter
    got = kinds("\\begin {verbatim}\\x{\\end{verbatim}\\y")
    assert ("verbatim", "\\x{") in got and got[-1] == ("word", r"\y")
    assert kinds("\\begin{verbatim}\\x")[-1] == ("verbatim", "\\x")  # never closed: to the end
    assert kinds("\\begin{verbatim}\\end{verbatim}")[-1] == ("close", "}")  # empty
    assert kinds("\\begin{center}\\x")[-1] == ("word", r"\x")


def test_a_definition_is_read_with_its_signature_and_where_it_is():
    text = r"\newcommand*{\a}[2][x]{#1}" + "\n" + r"\providecommand\b[1]{}\newenvironment*{c}[1]{}{}\newcommand\d{}"
    assert read(text) == {"a": "[2][]", "b": "[1]", "c": "[1]", "d": ""}
    first = declarations(text)[0]
    assert text[first.start : first.end] == r"\newcommand*{\a}"


def test_def_reads_the_parameter_text():
    assert read(r"\def\a#1#2{}\gdef\b{}\def\c#1.#2{}\def\d#{}\def\e") == {
        "a": "[2]",
        "b": "",
        "c": "?",
        "d": "?",
        "e": "?",
    }
    assert read(r"\def\a#1{\newcommand{\inner}[3]{}}") == {"a": "[1]", "inner": "[3]"}


def test_text_that_does_not_typeset_declares_nothing():
    assert read("% \\newcommand\\a{}\n\\newcommand\\b{}") == {"b": ""}
    assert read(r"\verb|\newcommand\a{}|\newcommand\b{}") == {"b": ""}
    assert read("\\begin{verbatim}\\newcommand\\a{}\\end{verbatim}\\newcommand\\b{}") == {"b": ""}
    assert read(r"\string\newcommand\a \noexpand\newcommand\b \newcommand\c{}") == {"c": ""}


def test_iffalse_is_dead_until_its_else_or_fi():
    text = r"\iffalse \newcommand\a{} \ifx\x\y \fi \newcommand\b{} \else \newcommand\c{} \fi \newcommand\d{}"
    assert read(text) == {"c": "", "d": ""}
    assert read(r"\newif\ifdead \iffalse \ifdead \newcommand\a{}\fi \fi \newcommand\b{}") == {
        "ifdead": "",
        "deadtrue": "",
        "deadfalse": "",
        "b": "",
    }
    assert read(r"\iffalse \if@x \newcommand\a{}\fi \newcommand\b{} \fi \newcommand\c{}") == {"c": ""}
    assert read(r"\iffalse \newcommand\a{}") == {}  # never closed: dead to the end


def test_the_other_forms():
    text = (
        r"\newlength{\l}\newsavebox\s\newfontfamily\f[x]{Font}\newtoggle{t}\newif\iffoo\newcounter{n}"
        r"\definecolor{ink}{rgb}{0,0,1}\colorlet{ b b }{ink}"
    )
    forms = {d.name: d.form for d in declarations(text)}
    assert forms == {
        "l": Form.REGISTER,
        "s": Form.REGISTER,
        "f": Form.REGISTER,
        "t": Form.REGISTER,
        "iffoo": Form.REGISTER,
        "footrue": Form.REGISTER,
        "foofalse": Form.REGISTER,
        "n": Form.COUNTER,
        "ink": Form.COLOUR,
        "b b": Form.COLOUR,
    }


def test_xparse_and_expl3_definitions():
    text = (
        r"\NewDocumentCommand{\a}{ s O{x} m }{}\NewDocumentEnvironment{b}{}{}{}\NewDocumentCommand\c"
        "\n"
        r"\ExplSyntaxOn \cs_new:Npn \d_e:nnN #1#2#3 {} \cs_new_protected:Nn \f:n {} \cs_new:Nn \g {} \ExplSyntaxOff"
    )
    assert read(text) == {"a": "som", "b": "", "c": "?", "d_e:nnN": "[3]", "f:n": "[1]"}
    assert read(r"\NewDocumentCommand{\a}{m") == {"a": "?"}
    assert read(r"\newcommand \newcommand{\x}{} \newenvironment{\x}") == {"newcommand": "", "x": ""}  # as TeX reads it
    assert read(r"\newcommand{\a b}\newcommand") == {}


def test_xparse_letters_without_a_default_or_with_one_that_never_closes():
    assert xparse_letters("O m") == "om" and xparse_letters("O{x") == "?"
    assert read(r"\NewDocumentCommand 5 \NewDocumentEnvironment{}") == {}


def test_only_tex_spaces_are_spaces():
    text = "a\u00a0b\u2028c\x0cd"  # a no-break space and a form feed are characters to TeX, not spaces
    assert [t.kind for t in tokenize(text)] == [Kind.CHAR] * len(text)
    assert detokenized("\u00a0 a") == "\u00a0 a"


def test_an_iffalse_that_let_copies_is_no_test():
    assert read(r"\let\ifa\iffalse \newcommand\a{} \let\ifb=\iffalse \newcommand\b{}") == {"a": "", "b": ""}
    assert read(r"\iffalse \let\ifa\iffalse \newcommand\a{} \fi \newcommand\b{}") == {"b": ""}


def test_a_catcode_switch_ends_with_its_group():
    for open_, close in (("{", "}"), (r"\begingroup", r"\endgroup"), (r"\begin{x}", r"\end{x}")):
        words = [
            t.text
            for t in tokenize(f"{open_}\\makeatother\\a@b{close}\\a@b")
            if t.kind is Kind.WORD and t.text.startswith(r"\a")
        ]
        assert words == [r"\a", r"\a@b"], open_
    assert tokenize(r"}\makeatother \a@b")[-1].text == "b"  # a stray `}` closes nothing


def test_an_iffalse_in_a_list_is_no_test():
    assert read(r"\DoNotIndex{\iffalse,\fi}\newcommand\a{}") == {"a": ""}


def test_control_words_are_the_ones_that_run():
    text = "\\a % \\b\n\\string\\c \\noexpand\\d \\verb|\\e| \\f\\g"
    assert control_words(text) == ["a", "string", "noexpand", "verb", "f", "g"]


def test_characters_are_counted_outside_groups_comments_and_escapes():
    assert count_outside_groups(r"a & {b & c} \& d % &" + "\n& e", "&") == 2


def test_braces_balance_by_tokens():
    assert is_balanced(r"{a \{ } % }") and is_balanced(r"\verb|{|") and is_balanced("")
    assert not is_balanced("{") and not is_balanced("}{")


def test_a_call_is_its_optional_and_required_argument_and_nothing_else():
    assert call_text(r"\inc [w=1,a={]}] {p}", "inc") == ("w=1,a={]}", "p")
    assert call_text(r"\inc{}", "inc") == (None, "")
    assert call_text(r"\inc[x]", "inc") is None  # no required argument
    assert call_text(r"\inc{p}{q}", "inc") is None
    assert call_text(r"\inc[x{p}", "inc") is None  # the [ never closes: it is not an optional argument
    assert call_text(r"\other{p}", "inc") is None and call_text("", "inc") is None


def test_loaders_are_read_with_their_options_and_names():
    text = r"""
\RequirePackage[a={]},b]{one, two}\usepackage {three}
\iffalse \usepackage{dead} \fi
% \usepackage{comment}
\usepackage\x \LoadClass[x]{cls} \usepackage{}
"""
    loads = [(d.signature, d.name) for d in declarations(text) if d.form is Form.LOAD]
    assert loads == [("RequirePackage", "one, two"), ("usepackage", "three"), ("LoadClass", "cls"), ("usepackage", "")]


@given(st.text())
def test_any_text_is_tokenized_and_covered(text):
    """Any characters at all, a no-break space and a line separator included (a real file crashed the tokenizer)."""
    assert "".join(t.text for t in tokenize(text)) == text
    declarations(text)


def test_detokenize_shows_an_argument_as_tex_does():
    def shown(text: str) -> str:
        return detokenize(tokenize(text, at_letter=False))

    assert shown(r"\a  b #1 ##") == r"\a b ##1 ####"
    assert shown("x% c\n y\n\nz \\relax % c\n w") == r"xy \par z \relax w"  # a comment eats the next line's indent
    assert shown(r"\  \& a") == r"\ \& a"


def test_names_are_read_whole():
    text = r"\newenvironment{equation*}{}{} \newenvironment{math-function}[1]{}{} \newtoggle{bbx:isbn}"
    assert read(text) == {"equation*": "", "math-function": "[1]", "bbx:isbn": ""}


def test_expl3_functions_are_declared_with_the_arguments_their_name_says():
    found = {
        d.name: d.signature
        for d in declarations(r"\cs_new:Npn \ac_foo:nn #1#2 {} \cs_new_protected:Nn \ac_bar: {}", expl3=True)
    }
    assert found == {"ac_foo:nn": "[2]", "ac_bar:": ""}
    assert read(r"\cs_new:Npn \ac_foo:nn #1#2 {}") == {}  # without expl3 syntax these are not words
    assert read(r"\ExplSyntaxOn \cs_new:Npn \ac_foo:nn #1#2 {} \ExplSyntaxOff") == {"ac_foo:nn": "[2]"}
