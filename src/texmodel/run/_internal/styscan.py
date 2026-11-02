"""What a `.sty` or `.cls` file asks TeX to load (D2): the files `\\RequirePackage` and its kin name.

A scan, not an expansion: a name built from a macro (`\\RequirePackage{\\pkg}`) cannot be known and is reported as
unchecked, never guessed.
"""

import re
from collections.abc import Iterable

from texmodel._internal.tex import Form, declarations

SAFE_NAME = re.compile(r"[A-Za-z0-9._-]+")  # also the only names the toolchain probe will take on a shell line


def _file(cmd: str, name: str) -> str:
    if cmd == "tcbuselibrary":
        return f"tcb{name}.code.tex"
    return f"{name}.cls" if cmd.startswith("LoadClass") else f"{name}.sty"


def needed(texts: Iterable[str]) -> tuple[list[str], list[str]]:
    """The files named in `texts`, in order and once, and the names that are not plain file names (unchecked)."""
    files: dict[str, None] = {}
    unchecked: dict[str, None] = {}
    for text in texts:
        for load in (d for d in declarations(text) if d.form is Form.LOAD):
            for name in (n.strip() for n in load.name.split(",")):
                if not name:
                    continue
                if SAFE_NAME.fullmatch(name):
                    files[_file(load.signature, name)] = None
                else:
                    unchecked[name] = None
    return list(files), list(unchecked)
