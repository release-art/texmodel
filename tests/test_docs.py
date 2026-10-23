"""The `python` blocks of the README and of the docs pages run, a page's blocks in order as one module: an example that
stops working fails here. A block that only illustrates is fenced `py`."""

import pathlib
import re
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).parent.parent
SKIPPED = {"texmodel-plan.md", "known-limitations.md"}  # specification and notes, not examples
PAGES = [
    ROOT / "README.md",
    *(p for p in sorted((ROOT / "docs").rglob("*.md")) if "briefs" not in p.parts and p.name not in SKIPPED),
]


FENCE = r"```python\n(.*?)```"
PAGES = [
    p for p in PAGES if re.search(FENCE, p.read_text(encoding="utf-8"), re.DOTALL)
]  # build.md and check.md have none


@pytest.mark.parametrize("page", PAGES, ids=[p.relative_to(ROOT).as_posix() for p in PAGES])
def test_python_blocks_of_a_page_run(page: pathlib.Path, capsys: pytest.CaptureFixture[str]):
    blocks = re.findall(FENCE, page.read_text(encoding="utf-8"), re.DOTALL)
    module = types.ModuleType("doc_page")
    sys.modules[module.__name__] = module
    try:
        for n, block in enumerate(blocks, 1):
            exec(compile(block, f"{page}:block {n}", "exec"), module.__dict__)  # noqa: S102
    finally:
        del sys.modules[module.__name__]
    capsys.readouterr()
