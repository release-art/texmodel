# Arguments

A field is an argument. Its type says what it holds, and `arg(...)` says how it is written. The blocks on this page run in
order, as one module.

```python
import enum

from texmodel.components import Command
from texmodel.interface import PAREN, SQUARE, Gap, Star, arg
from texmodel.package import Package
from texmodel.types import Choice, Length, Raw, Text

pkg = Package("args-demo", prefix="ad", adopted=True)  # adopted: only the declarations matter here
```

## The default signature

Without `arg()`, a required field is `{...}` and an optional field (one with a default) is TeX's one optional argument,
`[...]`, written first, as `\newcommand` has it. Optional fields are keyword-only in Python.

```python
@pkg.command
class Slot(Command):
    """A labelled paragraph."""

    text: Text
    label: Text | None = None      # \adSlot[label]{text}


assert Slot(text="a", label="L").render() == r"\adSlot[L]{a}"
assert Slot(text="a").render() == r"\adSlot{a}"
```

Write an optional field as `arg(default=...)` (`label: Text | None = arg(default=None)`): a type checker then reads it as
keyword-only and accepts a required field after it, where a plain `= None` is reported as a field-order error although it
runs.

## Any signature with `arg()`

With `arg()` the slot keeps its declaration order, so any signature can be stated. In Python a field with `arg()` is keyword-only,
whether or not it is optional.

```python
@enum.unique
class BoxAlign(Choice):
    CENTRE = "c"
    LEFT = "l"


@pkg.command
class MakeBox(Command):
    """\\makebox[3cm][c]{x}"""

    cs = "makebox"
    width: Length | None = arg(SQUARE, default=None, fill=Gap.REFUSE)   # `[c]` alone is not valid: refused
    align: BoxAlign | None = arg(SQUARE, default=None)
    text: Raw


@pkg.command
class Section(Command):
    """\\section*[short]{long}"""

    cs = "section"
    starred: Star = arg(default=False)                 # a token: `*`
    short: Text | None = arg(SQUARE, default=None)
    title: Text


@pkg.command
class Put(Command):
    """\\put(1,2){x}"""

    cs = "put"
    at: tuple[int, int] = arg(PAREN)                   # a tuple, written `1,2` (`sep=` changes the comma)
    text: Raw


assert MakeBox(text=Raw("x"), width=Length("3cm"), align=BoxAlign.CENTRE).render() == r"\makebox[3cm][c]{x}"
assert Section(title="Long", starred=True, short="S").render() == r"\section*[S]{Long}"
assert Put(text=Raw("x"), at=(1, 2)).render() == r"\put(1,2){x}"
```

- **Delimiters.** `{}` `[]` `()` `<>` or your own `Delimiter`; a `Star` or another token.
- **Left-out slots.** A slot left out is not written. An optional slot left out before a later optional one writes `fill=`
  (say `""` for empty brackets) or is refused (`Gap.REFUSE`). Two optionals without saying which is first is `TM-M037`.
- **Groups.** A `SlotGroup` is written together or not at all.
- **Definitions.** A signature `\newcommand` can define keeps it. Several optional arguments, other delimiters or a token
  are defined with `\NewDocumentCommand` / `\NewDocumentEnvironment` (xparse, in the kernel). The arguments are `#1`... in
  TeX order; an optional one left out is empty, and a token is `\BooleanTrue` or `\BooleanFalse`.

## Value types

| Type | Written as |
|---|---|
| `Text` | escaped |
| `PdfString` | for the inside of a PDF literal string: [Values](values.md#pdf-strings) |
| `Raw` | as it is |
| `Length` | `Length("2mm")`, or `Length.expr(r"\linewidth")` for a TeX expression |
| `CMYK`, `RGB`, `Gray` | colour components in [0, 1], no conversion between models |
| `ColourName` | an xcolor name or expression, checked against the package ([Colour names](values.md#colour-names)) |
| `int`, `float` | the number; a float is rounded to five decimals |
| `bool` | `true` / `false` |
| `Choice` | the member's TeX |
| tuple, `NamedTuple`, dataclass, model, `list` | of those; a `list` repeats |
| `KeyVals` | a key list, below |

A wrong value is a violation with the field's path.

## Key lists

A key list (`\adjustbox{max width=\linewidth, center}{...}`) is a `KeyVals`, a frozen pydantic model. Its field types say how
each item is written, and its `KeyRules` say how the library reads it.

```python
from texmodel.interface import Flag, Item, OptionalValue, Switch
from texmodel.keys import PGFKEYS
from texmodel.keyvals import Entry, KeyVals, key


class AdjustOptions(KeyVals, rules=PGFKEYS):
    max_width: Length | None = key("max width")                       # max width=3cm
    center: Flag = False                                              # center
    clip: Switch | None = None                                        # clip=true / clip=false
    rounded: OptionalValue[Length] | None = key("rounded corners")    # rounded corners  /  rounded corners=2pt
    tags: list[Text] | None = None                                    # tags=a,tags=b   (a list repeats the key)
    extra: Item[Raw] | None = None                                    # anything else, as written
    rules: list[Item[Entry]] | None = None                            # cell{1}{2}={bg=red}  (an item that spells its own key)


@pkg.command
class AdjustBox(Command):
    """\\adjustbox[options]{x}"""

    cs = "adjustbox"
    options: AdjustOptions | None = None
    text: Raw


box = AdjustBox(text=Raw("x"), options=AdjustOptions(max_width=Length.expr(r"\linewidth"), center=True))
assert box.render() == r"\adjustbox[max width=\linewidth,center]{x}"
```

Items are written in declaration order and unset ones are left out. A `Text` value the library would split (`,` `=` `]`)
is put in braces. `exclusive` and `requires` on the class refuse combinations.

Presets in `texmodel.keys` (`PGFKEYS`, `XKEYVAL`, `KVOPTIONS`, `L3KEYS`, `KEYVAL`) hold what a library does;
`dataclasses.replace(PGFKEYS, booleans=("on", "off"))` makes another. They were measured, not assumed:
`tests/test_texmodel/test_interface_tex.py` passes awkward values through pgfkeys, xkeyval, keyval and l3keys. All four
read `,` `=` `]` safely when braced and strip a space at either end of a value. `KVOPTIONS` is `XKEYVAL` without nesting
and was not measured.
