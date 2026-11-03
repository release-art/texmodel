"""Reading an argument back: the inverse of `FieldType.text`, for the text TeX handed a stub (`\\detokenize`d: a space
after each control word, runs of spaces one)."""

from ..errors import Violation
from ..plan import FieldEdit
from .fieldtypes import Style
from .render import Arg


def read_field(a: Arg, text: str) -> FieldEdit:
    """One argument's text (as `\\detokenize` shows it) as a `FieldEdit`: the typed value it reads back to. An optional
    argument left out or empty has no value. A text that is not a value of the field's type has a `Violation`
    (`TM-C021`) whose path is the field; what the text cannot say (a colour's model, a key list) has neither."""
    if a.optional and not a.token and not text:
        return FieldEdit(a.name, text)
    try:
        return FieldEdit(a.name, text, a.type.read(text, Style(booleans=a.booleans, sep=a.sep)))
    except NotImplementedError:
        return FieldEdit(a.name, text)
    except ValueError as exc:
        hint = f"expected {a.type.describe()}"
        return FieldEdit(a.name, text, violation=Violation("TM-C021", a.name, f"{a.name}: {exc}", hint=hint))
