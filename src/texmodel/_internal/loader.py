"""Find what a project names with a pointer: its `Package` (`[tool.texmodel] package`) or a document."""

import importlib
import pathlib
import re
import sys
from typing import Any

from ..errors import DeclarationError
from ..package import Package
from ..plan import Plan

_POINTER = re.compile(
    r"(?P<module>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*):(?P<attr>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)(?P<call>\(\))?"
)


def _load(spec: str, root: pathlib.Path, what: str) -> Any:  # noqa: ANN401  # whatever the project put there
    """Resolve a pointer: `pkg.module:object`, `pkg.module:namespace.object` or `pkg.module:get_object()`, looking in
    `root` and `root/src` first. A trailing `()` calls the object with no arguments and uses what it returns."""
    if not (m := _POINTER.fullmatch(spec)):
        raise DeclarationError(
            f"{spec!r} must be 'module:object', 'module:namespace.object' or 'module:getter()'",
            code="TM-D020",
            hint="the module part is dotted, the object part is a name or a dotted path to one",
        )
    for path in (root, root / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    try:
        obj: Any = importlib.import_module(m["module"])
        for name in m["attr"].split("."):
            obj = getattr(obj, name)
        return obj() if m["call"] else obj
    except (ImportError, AttributeError, TypeError) as exc:
        raise DeclarationError(f"cannot load {spec!r}: {exc}", code="TM-D021", hint=f"check {what}") from exc


def load_package(spec: str, root: pathlib.Path) -> Package:
    """Require the loaded object to be a `Package`."""
    package = _load(spec, root, "[tool.texmodel] package")
    if not isinstance(package, Package):
        raise DeclarationError(f"{spec!r} is a {type(package).__name__}, not a Package", code="TM-D022")
    return package


def load_document(spec: str, root: pathlib.Path) -> str | Plan:
    """The document: a `str` (`Package.document()`) or a `Plan` (`Package.plan()`), or a function returning one."""
    obj = _load(spec, root, "the module:attribute you passed")
    text = obj() if callable(obj) else obj
    if not isinstance(text, str | Plan):
        raise DeclarationError(
            f"{spec!r} is a {type(text).__name__}, not a document",
            code="TM-D024",
            hint="point at a str or Plan from Package.document() / plan(), or a function returning one",
        )
    return text
