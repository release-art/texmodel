"""The python blocks of docs/cookbook.md run: an example that stops working fails here."""

import pathlib
import re
import sys
import types

import pytest

DOC = pathlib.Path(__file__).parent.parent / "docs" / "cookbook.md"
BLOCKS = re.findall(r"```python\n(.*?)```", DOC.read_text(encoding="utf-8"), re.DOTALL)


@pytest.mark.parametrize("block", BLOCKS, ids=[b.splitlines()[0][:40] for b in BLOCKS])
def test_cookbook_block_runs(block: str, capsys: pytest.CaptureFixture[str]):
    module = types.ModuleType("cookbook_block")
    sys.modules[module.__name__] = module
    try:
        exec(compile(block, str(DOC), "exec"), module.__dict__)  # noqa: S102
    finally:
        del sys.modules[module.__name__]
    capsys.readouterr()
