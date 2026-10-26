# Programs that read components

For code that builds deck models, reference pages or checks from the declarations. The blocks on this page run in order,
as one module.

```python
from texmodel.components import Command, Value, control_name, describe, field
from texmodel.package import Package, declared, setting_line
from texmodel.types import CMYK, Colour, Length, Raw, Text

pkg = Package("brand", prefix="bb")
```

## What is public on a component

An attribute without a leading underscore is public and read-only. On a component: `cs`, `syntax`, `defined_by`, `meta` and
(an `Environment`'s) `children`. On a `Value` also `default`, `colour_name` and `needs_packages`. Read them; do not assign them
after the class is registered. `meta` is the mapping given in the class body (`meta = {"audience": "deck"}`), written to the
schema as `x-audience`.

Anything starting with `_`, including every `__tm_*` attribute, is internal and may change in any release.

## Describe a component

`describe(cls)` reports a registered command, environment or value as a frozen `Description`:

| Field | Meaning |
|---|---|
| `category` | `"command"`, `"environment"` or `"value"` |
| `name` | the class name |
| `cs` | the control sequence without the backslash; `None` for a colour |
| `doc` | the docstring |
| `arguments` | `ArgumentInfo(name, optional, doc)` in TeX order; empty for a value |
| `python` | a value's Python type (`bool`, `Length`, `str`, `Raw`, `Colour`) |
| `default` | a value's default |
| `colour_name` | a colour's name |
| `body`, `end` | the declared TeX with `#name` holes: a command's `body`, an environment's `begin` and `end`; `None` for a value or a component another source defines |

```python
@pkg.command
class Name(Command):
    """The subject's name, set as the title."""

    name: Raw = field(doc="the subject's name")
    note: Raw | None = None
    body = r"\textbf{#name}#note"


@pkg.value
class CardWidth(Value[Length]):
    """A6 short edge."""

    default = Length("105mm")


@pkg.value
class TechCut(Value[Colour]):
    """The cut line."""

    default = CMYK(0, 0, 0.4, 0)
    colour_name = "bbTechCut"


d = describe(Name)
assert (d.category, d.cs, d.doc) == ("command", "bbName", "The subject's name, set as the title.")
assert [(a.name, a.optional, a.doc) for a in d.arguments] == [("name", False, "the subject's name"), ("note", True, None)]
assert (describe(CardWidth).python, describe(CardWidth).default) == (Length, Length("105mm"))
assert describe(TechCut).cs is None
assert d.body == r"\textbf{#name}#note"
```

An unregistered class is `TM-M019`. `control_name(cls)` and `Value.declared_default()` are the narrower ways to the control
sequence and the default.

## Declare components at run time

When a program decides the names, `pkg.make_command` and `pkg.make_value` build the class and register it, as the
decorators do:

```python
title = pkg.make_command("Title", "the title", fields={"text": (Raw, field(doc="the title"))}, body=r"\bb@title{#text}")
cut = pkg.make_value("Bleed", Length, "the bleed", default=Length("3mm"))
```

`fields` maps a name to `(hint, field(...))` in TeX order, as pydantic's `create_model` does. Declaring the same data again
returns the class made first, so several series can share a macro. Other data under the same name is `TM-M007`. `module`
(default: the package's name) is the module shown in messages.

```python
assert pkg.make_value("Bleed", Length, "the bleed", default=Length("3mm")) is cut
```

## Write a setting, read a scan

`setting_line(value)` is the line a document writes for one setting.

```python
assert setting_line(CardWidth(Length("100mm"))) == r"\setlength{\bbCardWidth}{100mm}"
```

`declared(text)` is the set of control sequences the adoption scanner reads in a text:
[TeX you already have](adopting.md).
