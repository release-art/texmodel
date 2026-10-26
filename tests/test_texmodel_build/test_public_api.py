"""The public/private line of texmodel-build: top-level modules are public, everything else is in ``_internal``."""

import pkgutil

import texmodel_build

PUBLIC = {
    "cli", "compiler", "config", "diagnostics", "engines", "errors", "hand_edits", "result", "targets",
    "testkit", "verify",
}  # fmt: skip


def test_only_the_public_modules_sit_at_the_top_level():
    top = {m.name for m in pkgutil.iter_modules(texmodel_build.__path__)}
    assert top - {"_internal"} == PUBLIC
