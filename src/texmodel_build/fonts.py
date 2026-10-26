"""The font files a compile embedded, read from its LuaTeX log (A7, A8). luaotfload falls back to a system font for
one it cannot find, without an error; a document that must be self-contained checks where every font came from. A font
inside an included PDF is not in the log."""

import pathlib
import re
from collections.abc import Sequence

# LuaTeX ends the log with `</path/a.otf></path/b.pfb><./c.ttf>` after the memory statistics, one `<file>` per font.
_LISTING = re.compile(r"stack positions out of[^\n]*\n(.*?)\nOutput written on", re.DOTALL)
_FILE = re.compile(r"<([^<>]+)>")


def embedded(log: str, cwd: pathlib.Path) -> list[pathlib.Path]:
    """The font files `log` lists, in the order listed, resolved against `cwd` (the directory of the source, where
    the compile ran) when relative. Empty when the compile embedded none or did not finish. The paths are as the
    compiler saw them: inside the image when it ran in one."""
    listing = _LISTING.search(log)
    if not listing:
        return []
    return [(cwd / name.replace("\n", "")).resolve() for name in _FILE.findall(listing[1])]


def outside(log: str, allowed: Sequence[pathlib.Path], cwd: pathlib.Path) -> list[pathlib.Path]:
    """The embedded fonts that are not under any of the `allowed` directories."""
    roots = [(cwd / d).resolve() for d in allowed]
    return [f for f in embedded(log, cwd) if not any(f.is_relative_to(r) for r in roots)]


__all__ = ["embedded", "outside"]
