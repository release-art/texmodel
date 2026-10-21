"""The one place a process starts (C3): argv lists only, never a shell string.

import-linter forbids importing `subprocess` anywhere else.
"""

import dataclasses
import pathlib
import subprocess
from collections.abc import Sequence

from ..errors import ToolchainError


@dataclasses.dataclass(frozen=True)
class Proc:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def text(data: str | bytes | None) -> str:
    return data.decode(errors="replace") if isinstance(data, bytes) else (data or "")


def spawn(argv: Sequence[str], *, cwd: pathlib.Path | None, env: dict[str, str], timeout: float | None) -> Proc:
    """The one place a process starts."""
    try:
        done = subprocess.run(  # noqa: S603
            list(argv), cwd=cwd, env=env, capture_output=True, text=True, errors="replace", timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        return Proc(-1, text(exc.stdout), text(exc.stderr), timed_out=True)
    except FileNotFoundError as exc:
        raise ToolchainError(f"{argv[0]}: not found", code="TM-T001", hint="run `texmodel-build doctor`") from exc
    return Proc(done.returncode, done.stdout, done.stderr)
