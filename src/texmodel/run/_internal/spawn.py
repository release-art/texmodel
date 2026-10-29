"""The one place a process starts (C3): argv lists only, never a shell string.

import-linter forbids importing `subprocess` anywhere, and a test forbids `create_subprocess` outside this module.
"""

import asyncio
import contextlib
import dataclasses
import pathlib
from collections.abc import Sequence

from ..errors import ToolchainError


@dataclasses.dataclass(frozen=True)
class Proc:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def text(data: bytes) -> str:
    return data.decode(errors="replace")


async def spawn(argv: Sequence[str], *, cwd: pathlib.Path | None, env: dict[str, str], timeout: float | None) -> Proc:
    """The one place a process starts. Past `timeout`, or when the caller is cancelled, the process is killed and
    reaped before this returns or re-raises: nothing outlives the call."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError as exc:
        raise ToolchainError(f"{argv[0]}: not found", code="TM-T001", hint="run `texmodel run doctor`") from exc
    assert proc.stdout and proc.stderr
    # read while waiting, so a full pipe never blocks the child; a killed child closes them, so what it wrote is kept
    reads = asyncio.gather(proc.stdout.read(), proc.stderr.read())
    timed_out = False
    try:
        async with asyncio.timeout(timeout):
            returncode = await proc.wait()
    except TimeoutError:
        await _kill(proc)
        returncode, timed_out = -1, True
    except asyncio.CancelledError:
        await _kill(proc)
        reads.cancel()
        raise
    out, err = await reads
    return Proc(returncode, text(out), text(err), timed_out=timed_out)


async def _kill(proc: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError):  # it ended on its own meanwhile
        proc.kill()
    await proc.wait()
