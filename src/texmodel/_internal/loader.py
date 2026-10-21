"""Find the `Package` a project declares in `[tool.texmodel] package = "module:attribute"`."""

import importlib
import pathlib
import sys

from ..errors import DeclarationError
from ..package import Package


def load_package(spec: str, root: pathlib.Path) -> Package:
    """Import `module:attribute`, looking in `root` and `root/src` first, and require it to be a `Package`."""
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise DeclarationError(f"package = {spec!r} must be 'module:attribute'", code="TM-D020")
    for path in (root, root / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    try:
        package = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        raise DeclarationError(
            f"cannot load {spec!r}: {exc}", code="TM-D021", hint="check [tool.texmodel] package"
        ) from exc
    if not isinstance(package, Package):
        raise DeclarationError(f"{spec!r} is a {type(package).__name__}, not a Package", code="TM-D022")
    return package
