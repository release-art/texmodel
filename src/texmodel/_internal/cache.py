"""Content-addressed compile cache (C12). A key covers everything that can change the output."""

import hashlib
import json
import pathlib
import shutil
from collections.abc import Sequence
from typing import Protocol

from ..result import CompileResult


class Hasher(Protocol):
    def update(self, data: bytes, /) -> None: ...


_SKIP_DIRS = {".git", ".texmodel", "__pycache__", "node_modules", ".venv"}


def _tree(h: Hasher, root: pathlib.Path) -> None:
    # ponytail: hashes every file under the dir on each compile; keep sources in a dedicated dir, or add an mtime index.
    for path in sorted(root.rglob("*")):
        if path.is_file() and not _SKIP_DIRS.intersection(path.relative_to(root).parts):
            h.update(path.relative_to(root).as_posix().encode() + b"\0")
            h.update(hashlib.file_digest(path.open("rb"), "sha256").digest())


def cache_key(
    source: pathlib.Path,
    roots: Sequence[pathlib.Path],
    *,
    image_digest: str | None,
    args: Sequence[str],
    epoch: int | None,
) -> str:
    h = hashlib.sha256()
    h.update(json.dumps([source.name, image_digest, list(args), epoch]).encode())
    for root in (source.parent, *roots):
        h.update(b"\1" + str(len(root.parts)).encode())  # separates roots, not their absolute location
        _tree(h, root)
    return h.hexdigest()


def load(cache_dir: pathlib.Path, key: str, outdir: pathlib.Path) -> CompileResult | None:
    """A hit copies the stored PDF and log into `outdir` and returns the stored result, marked as a hit."""
    entry = cache_dir / key
    stored = entry / "result.json"
    if not stored.is_file():
        return None
    data = json.loads(stored.read_text(encoding="utf-8"))
    outdir.mkdir(parents=True, exist_ok=True)
    for name in ("pdf", "log"):
        if data.get(name):
            shutil.copy2(entry / pathlib.Path(data[name]).name, outdir / pathlib.Path(data[name]).name)
            data[name] = str(outdir / pathlib.Path(data[name]).name)
    return CompileResult.from_dict(data, cache_hit=True)


def store(cache_dir: pathlib.Path, key: str, result: CompileResult) -> None:
    """Only complete results are stored (the caller checks); written to a temp dir then renamed."""
    entry = cache_dir / key
    tmp = cache_dir / f".{key}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for path in (result.pdf, result.log):
        if path:
            shutil.copy2(path, tmp / path.name)
    (tmp / "result.json").write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    shutil.rmtree(entry, ignore_errors=True)
    tmp.rename(entry)
