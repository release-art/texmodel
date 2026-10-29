"""The public API as a reviewed snapshot (plan I2, A9): every name in a public module's `__all__`, with its signature,
and the public methods of its classes. A change to the API is a change to `fixtures/public_api.txt`, read in review;
after an intended one, `UPDATE_GOLDEN=1 pdm run pytest tests/test_api_snapshot.py`, then read the diff."""

import annotationlib
import functools
import importlib
import inspect
import os
import pathlib
import pkgutil
import types
from collections.abc import Callable

import pydantic

import texmodel
import texmodel_build

SNAPSHOT = pathlib.Path(__file__).parent / "fixtures" / "public_api.txt"


class _Elided:
    """A default, shown as `…`: its repr is runtime state (addresses, whole objects), its presence is the API."""

    def __repr__(self) -> str:
        return "…"


def _modules(package: types.ModuleType) -> list[types.ModuleType]:
    found: list[types.ModuleType] = []
    for info in pkgutil.iter_modules(package.__path__):
        if not info.name.startswith("_"):
            module = importlib.import_module(f"{package.__name__}.{info.name}")
            found += [module, *(_modules(module) if info.ispkg else ())]
    return found


def _signature(obj: Callable[..., object]) -> str:
    if isinstance(obj, type) and issubclass(obj, pydantic.BaseModel):  # its `__signature__` is rebuilt lazily
        fields = [
            f"{n}: {inspect.formatannotation(f.annotation)}" + ("" if f.is_required() else " = …")
            for n, f in obj.model_fields.items()
        ]
        return f"({', '.join(fields)})"
    try:
        sig = inspect.signature(obj, annotation_format=annotationlib.Format.STRING)
    except TypeError, ValueError:  # a builtin or an alias with no signature
        return ""
    elided = [p if p.default is p.empty else p.replace(default=_Elided()) for p in sig.parameters.values()]
    return sig.replace(parameters=elided).format(quote_annotation_strings=False)


def _line(name: str, obj: object) -> str:
    if callable(obj) and (isinstance(obj, type) or inspect.isroutine(obj)):
        return name + _signature(obj)
    return f"{name}: {type(obj).__name__}"


def snapshot() -> str:
    lines: list[str] = []
    for module in sorted(_modules(texmodel) + _modules(texmodel_build), key=lambda m: m.__name__):
        for name in sorted(getattr(module, "__all__", ())):
            obj = getattr(module, name)
            lines.append(_line(f"{module.__name__}.{name}", obj))
            if not isinstance(obj, type) or obj.__module__ != module.__name__:
                continue  # a re-export's members are listed where it is defined
            for member, value in sorted(vars(obj).items()):
                if member.startswith("_"):
                    continue
                if isinstance(value, property | functools.cached_property):
                    lines.append(f"{module.__name__}.{name}.{member}: property")
                elif inspect.isfunction(func := getattr(value, "__func__", value)):
                    lines.append(_line(f"{module.__name__}.{name}.{member}", func))
    return "\n".join(lines) + "\n"


def test_the_public_api_is_the_reviewed_snapshot():
    current = snapshot()
    if os.environ.get("UPDATE_GOLDEN"):
        SNAPSHOT.write_text(current, encoding="utf-8")
    assert SNAPSHOT.read_text(encoding="utf-8") == current, (
        "the public API changed: if intended, UPDATE_GOLDEN=1 and list it in CHANGELOG.md (I2)"
    )
