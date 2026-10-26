"""A document as one value (D1a, §21): its content and everything else a `.tex` carries.

```python
Document(
    Card(Name(text="Rex")),
    options=["a4paper"],
    settings=[FactGap(Length("3mm"))],
    preamble=PreambleSlots(after_package=(PdfInfo(Title="Rex"),)),
)
```

`Package.plan` and `Package.document` take one; given bare nodes they build the `Document` of those. `spec.to_dict`
and `spec.from_dict(package, data)` write and read it as data, and `spec.json_schema(package)` describes it.
"""

import dataclasses
import re
from collections.abc import Sequence

from .components import AnyValue, Node
from .preamble import PreambleSlots

OPTION = re.compile(r"[A-Za-z0-9][A-Za-z0-9=.-]*")  # a class option (`TM-C006`)


@dataclasses.dataclass(frozen=True, init=False)
class Document:
    """The nodes of a document and its class `options`, its `settings` (values set after the package loads) and the
    TeX it places around the class and package lines (`preamble`)."""

    content: tuple[Node, ...]
    options: tuple[str, ...]
    settings: tuple[AnyValue, ...]
    preamble: PreambleSlots

    def __init__(
        self,
        *content: Node,
        options: Sequence[str] = (),
        settings: Sequence[AnyValue] = (),
        preamble: PreambleSlots | None = None,
    ) -> None:
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "options", tuple(options))
        object.__setattr__(self, "settings", tuple(settings))
        object.__setattr__(self, "preamble", preamble or PreambleSlots())


__all__ = ["OPTION", "Document"]
