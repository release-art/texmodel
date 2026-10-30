r"""Components (M1): a `Command` is declared as a class; its fields are its arguments, its docstring its documentation.

```python
pkg = Package("acme-cards", prefix="ac")

@pkg.command
class Slot(Command):
    '''A labelled paragraph; the label prints as its heading.'''
    text: Text
    label: Text | None = None      # optional: keyword-only, rendered as TeX's one optional argument
```

An optional field's `Text`, `Raw`, number, flag or `Choice` default is TeX's too: `label: Text | None = "Note"` is
`\newcommand{\acSlot}[2][Note]{...}`; with no default it is `[]`.

`field(doc=..., meta={...})` and a class-level `meta = {...}` put a description and `x-` keys in the JSON Schema.

A `Value[T]` is a typed setting; its `default` is an instance of `T` and its type decides the TeX (M1a, T4, T5):

```python
@pkg.value
class FactGap(Value[Length]):
    '''Space under each fact.'''
    default = Length("2mm")
```

A `Value[Length]` may leave `default` out (a bare `\newlength`, set later); a `Value[Colour]` may rename itself
(`colour_name = "acInk"`). A package adds its own kinds with a `ValueKind` (`texmodel.types`): what it holds, the names
it claims, the TeX that declares and sets it, the packages it needs (a name, or a `Package` of this project). `Toggle`
in `texmodel.std.etoolbox` is one, built from etoolbox's own bindings:

```python
@pkg.value
class Draft(Value[Toggle]):
    '''Print the draft banner.'''
    default = False          # \newtoggle{acDraft} \togglefalse{acDraft}
```

An `Environment` also holds children, whose order and counts are its grammar (M4); a Doc is plain Python (D1):

```python
@pkg.environment
class CardBack(Environment):
    '''The back face of a card.'''
    children = [Name, Fact.times(2, 3), Slot.times(3)]     # Name: one; Fact: 2 to 3; Slot: 0 to 3
    # also `X.times.any()` (0 or more) and `X.times.at_least_one()` (1 or more)
    begin = r'\begin{minipage}{\linewidth}'
    end = r'\end{minipage}'

pkg.document(CardBack(Name(text="Rex"), Fact(text="Friendly & loyal."), Fact(text="50% of $5")))
```

`Text` fields are escaped on render (T3); a `Raw` field passes TeX through.

A body is TeX, given explicitly: a `body` method returning it (a plain `body = r"..."` string works too), or a
`TemplateRef` to a file. Indentation is removed, so a triple-quoted raw string reads as it will render:

```python
class Title(Command):
    '''A job title.'''
    text: Text

    def body(self):
        return r'''
            \par\noindent{\color{bc-accent}#text}\par
        '''

class Slot(Command):
    '''A labelled paragraph.'''
    text: Text

    def body(self):
        return TemplateRef("slot.tex")      # relative to this module; nothing is looked up by name
```

An environment has `begin` and `end` in the same way. The method is read once, when the class is defined, with no
instance: keep it to constant TeX. Inside a body `#text` is the argument named `text`. A bad declaration is refused when
the class is defined.
"""

from .._internal.specs import control_name
from ._describe import ArgumentInfo, Description, describe
from ._node import ArgValue, Children, Command, Environment, Node, Passthrough, Resolved, Source, concrete_kinds, field
from ._terms import Anywhere, Repeat
from ._values import AnyValue, ColourRef, Value

__all__ = [
    "AnyValue",
    "Anywhere",
    "ArgValue",
    "ArgumentInfo",
    "Children",
    "ColourRef",
    "Command",
    "Description",
    "Environment",
    "Node",
    "Passthrough",
    "Repeat",
    "Resolved",
    "Source",
    "Value",
    "concrete_kinds",
    "control_name",
    "describe",
    "field",
]
