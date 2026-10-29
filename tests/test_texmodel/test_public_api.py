"""The public/private line: top-level modules are public API, everything else lives in ``_internal``."""

import importlib
import pkgutil

import pytest

import texmodel

PUBLIC = {
    "body",
    "bundle",
    "cli",
    "components",
    "config",
    "document",
    "drift",
    "ext",
    "errors",
    "history",
    "interface",
    "keys",
    "keyvals",
    "package",
    "plan",
    "pointer",
    "preamble",
    "testing",
    "spec",
    "std",
    "types",
}


def test_only_the_public_modules_sit_at_the_top_level():
    top = {m.name for m in pkgutil.iter_modules(texmodel.__path__)}
    assert top - {"_internal"} == PUBLIC, (
        "a new module is either public (add it here, document it) or goes in _internal"
    )


@pytest.mark.parametrize("name", sorted(PUBLIC - {"cli", "ext", "std"}))
def test_all_lists_what_a_module_offers(name):
    mod = importlib.import_module(f"texmodel.{name}")
    defined = {
        n for n, o in vars(mod).items() if not n.startswith("_") and getattr(o, "__module__", None) == mod.__name__
    }
    assert all(hasattr(mod, n) for n in mod.__all__)
    assert defined <= set(mod.__all__), "a new public name goes in __all__, or moves to _internal"
