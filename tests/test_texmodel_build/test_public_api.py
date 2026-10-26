"""The public/private line of texmodel-build: top-level modules are public, everything else is in ``_internal``."""

import importlib
import pkgutil

import pytest

import texmodel_build

PUBLIC = {
    "cli", "compiler", "config", "diagnostics", "engines", "errors", "hand_edits", "result", "targets",
    "testkit", "verify",
}  # fmt: skip


def test_only_the_public_modules_sit_at_the_top_level():
    top = {m.name for m in pkgutil.iter_modules(texmodel_build.__path__)}
    assert top - {"_internal"} == PUBLIC


@pytest.mark.parametrize("name", sorted(PUBLIC - {"cli"}))
def test_all_lists_what_a_module_offers(name):
    mod = importlib.import_module(f"texmodel_build.{name}")
    defined = {
        n for n, o in vars(mod).items() if not n.startswith("_") and getattr(o, "__module__", None) == mod.__name__
    }
    assert all(hasattr(mod, n) for n in mod.__all__)
    assert defined <= set(mod.__all__), "a new public name goes in __all__, or moves to _internal"
