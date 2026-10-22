"""Integration: every example package renders to exactly its committed golden (G7). See tests/examples/README.md."""

import importlib
import os
import pathlib
import re
import sys

import pytest

EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"
NAMES = sorted(p.name for p in EXAMPLES.iterdir() if (p / "__init__.py").is_file())
_STAMP = re.compile(r"generated with texmodel \d+\.\d+\.\d+")


def produced(name: str) -> dict[str, str]:
    """The files an example generates, with the generator version masked so a release does not churn the goldens."""
    sys.path.insert(0, str(EXAMPLES))
    try:
        module = importlib.import_module(name)
    finally:
        sys.path.remove(str(EXAMPLES))
    files = {f"{module.pkg.name}.sty": module.pkg.render(), **{f"{n}.tex": t for n, t in module.documents.items()}}
    return {path: _STAMP.sub("generated with texmodel X.Y.Z", text) for path, text in files.items()}


def test_there_are_examples():
    assert {"hello", "business_card", "letter"} <= set(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_an_example_renders_to_its_golden(name):
    expected = EXAMPLES / name / "expected"
    files = produced(name)
    if os.environ.get("UPDATE_GOLDEN"):
        expected.mkdir(exist_ok=True)
        for old in expected.iterdir():
            old.unlink()
        for path, text in files.items():
            (expected / path).write_text(text, encoding="utf-8")
    assert sorted(p.name for p in expected.iterdir()) == sorted(files), "golden files and generated files differ"
    for path, text in files.items():
        assert (expected / path).read_text(encoding="utf-8") == text, f"{name}/expected/{path} differs (G7)"
