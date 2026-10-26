"""Find what a project names with a pointer (`module:object`, `module:getter()`): its `Package`, a document or a `Plan`.
Public, so the build harness reads the same pointers."""

import importlib
import pathlib
import re
import sys
from collections.abc import Iterable, Sequence
from typing import Any, cast

from .errors import DeclarationError
from .package import Package
from .plan import Plan

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


def load_packages(spec: str | Sequence[str], root: pathlib.Path) -> tuple[Package, ...]:
    """A project's packages: one pointer or a list of them, each naming a `Package` or an iterable of `Package`s (a
    family: a core, its bases, one per series). In first-mention order; naming one twice counts once, and two different
    packages of one name are refused (`TM-D026`)."""
    found: dict[int, Package] = {}
    for one in [spec] if isinstance(spec, str) else spec:
        obj = _load(one, root, "[tool.texmodel] package")
        members: list[object] = (
            [obj]
            if isinstance(obj, Package)
            else list(cast("Iterable[object]", obj))
            if isinstance(obj, Iterable)
            else [obj]
        )
        for member in members:
            if not isinstance(member, Package):
                raise DeclarationError(
                    f"{one!r} gave a {type(member).__name__}, not a Package",
                    code="TM-D022",
                    hint="point at a Package, or at an iterable of them",
                )
            found.setdefault(id(member), member)
    packages = tuple(found.values())
    names = [p.name for p in packages]
    if clash := sorted({n for n in names if names.count(n) > 1}):
        raise DeclarationError(f"two packages are named {clash[0]!r}", code="TM-D026", hint="a package name is a file")
    return packages


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


def load_plan(spec: str, root: pathlib.Path) -> Plan:
    """The `Plan` a pointer names (`Package.plan()`), for the line-to-component map of a diagnostic (B2, D2)."""
    found = load_document(spec, root)
    if not isinstance(found, Plan):
        raise DeclarationError(
            f"{spec!r} is a str, not a Plan",
            code="TM-D025",
            hint="point at Package.plan(...) (or a function returning one): a str has no line-to-component map",
        )
    return found


__all__ = ["load_document", "load_packages", "load_plan"]
