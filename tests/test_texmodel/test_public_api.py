"""The public/private line: top-level modules are public API, everything else lives in ``_internal``."""

import pkgutil

import texmodel

PUBLIC = {"cli", "compiler", "config", "diagnostics", "engines", "errors", "result", "roots", "targets"}


def test_only_the_public_modules_sit_at_the_top_level():
    top = {m.name for m in pkgutil.iter_modules(texmodel.__path__)}
    assert top - {"_internal"} == PUBLIC, (
        "a new module is either public (add it here, document it) or goes in _internal"
    )
