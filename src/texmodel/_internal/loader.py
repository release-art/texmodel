"""Find what a project names as `module:attribute`: its `Package` (`[tool.texmodel] package`) or a document."""

import importlib
import pathlib
import sys
from typing import Any

from ..errors import DeclarationError
from ..package import Package


def _load(spec: str, root: pathlib.Path, what: str) -> Any:  # noqa: ANN401  # whatever the project put there
    """Import `module:attribute`, looking in `root` and `root/src` first."""
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise DeclarationError(f"package = {spec!r} must be 'module:attribute'", code="TM-D020")
    for path in (root, root / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    try:
        return getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        raise DeclarationError(f"cannot load {spec!r}: {exc}", code="TM-D021", hint=f"check {what}") from exc


def load_package(spec: str, root: pathlib.Path) -> Package:
    """Require the loaded object to be a `Package`."""
    package = _load(spec, root, "[tool.texmodel] package")
    if not isinstance(package, Package):
        raise DeclarationError(f"{spec!r} is a {type(package).__name__}, not a Package", code="TM-D022")
    return package


def load_document(spec: str, root: pathlib.Path) -> str:
    """The `.tex` text: the attribute is a `str` (from `Package.document()`), or a function that returns one."""
    obj = _load(spec, root, "the module:attribute you passed")
    text = obj() if callable(obj) else obj
    if not isinstance(text, str):
        raise DeclarationError(
            f"{spec!r} is a {type(text).__name__}, not a document",
            code="TM-D024",
            hint="point at a str from Package.document(), or a function returning one",
        )
    return text
