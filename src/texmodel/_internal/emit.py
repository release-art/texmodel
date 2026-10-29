"""A node tree as TeX: the call or `\\begin` line of each node, indented by its depth (G1).

What is written is chosen by `NodeKind`, data each node class carries, so the node classes import this module and not
the other way round."""

import enum
import typing
from typing import TYPE_CHECKING

from ..body import Comment
from .render import call_arguments
from .specs import control_name

if TYPE_CHECKING:
    from ..components import Command, Environment, Node, Passthrough


@enum.unique
class NodeKind(enum.Enum):
    """What a node is: a command (one call), an environment (`\\begin` ... `\\end` around its children) or the author's
    own TeX, written as it is."""

    COMMAND = "command"
    ENVIRONMENT = "environment"
    PASSTHROUGH = "passthrough"


INDENT = "  "  # per level of environment nesting; only lines texmodel writes take it (G1)


def call_line(node: "Command | Environment") -> tuple[str, tuple[tuple[str, int, int], ...]]:
    """The call of a command, or the `\\begin` line of an environment, and where each argument's text stands in it as
    `(field, start, end)` (delimiters excluded)."""
    cls = type(node)
    name = control_name(cls)
    args, spans = call_arguments(cls.__tm_args__, {a.name: getattr(node, a.name) for a in cls.__tm_args__})
    head = f"\\{name}" if cls.__tm_node__ is NodeKind.COMMAND else f"\\begin{{{name}}}"
    return head + args, tuple((arg, start + len(head), end + len(head)) for arg, start, end in spans)


def emit(node: "Node", depth: int = 0) -> str:
    """The TeX of a node at `depth`: the lines texmodel writes (`\\begin`, `\\end`, a call's first line, comments) take
    `INDENT` per level; a `Passthrough` and a call's continuation lines are the author's text, verbatim."""
    pad = INDENT * depth
    if isinstance(node, Comment):
        return "\n".join(pad + line if line else line for line in node.render().splitlines())
    kind = type(node).__tm_node__
    if kind is NodeKind.PASSTHROUGH:
        return typing.cast("Passthrough", node).tex.tex
    first = pad + call_line(typing.cast("Command | Environment", node))[0]
    if kind is NodeKind.COMMAND:
        return first
    environment = typing.cast("Environment", node)
    children = (emit(c, depth + 1) for c in environment.content)
    return "\n".join([first, *children, f"{pad}\\end{{{control_name(type(node))}}}"])
