"""The public/private line: top-level modules are public API, everything else lives in ``_internal``."""

import pkgutil

import texmodel

PUBLIC = {
    "bundle", "cli", "compiler", "config", "diagnostics", "drift", "engines", "errors", "result", "roots", "targets",
    "testkit", "verify",
}  # fmt: skip


def test_only_the_public_modules_sit_at_the_top_level():
    top = {m.name for m in pkgutil.iter_modules(texmodel.__path__)}
    assert top - {"_internal"} == PUBLIC, (
        "a new module is either public (add it here, document it) or goes in _internal"
    )
