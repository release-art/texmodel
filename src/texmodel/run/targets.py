"""Build every declared target (C10): reruns until stable are the compiler's, this adds concurrency and one summary."""

import asyncio
import dataclasses
import pathlib
from collections.abc import Iterable

from texmodel.pointer import load_plan

from .compiler import Compiler
from .config import Target
from .engines import get_engine
from .result import CompileResult


@dataclasses.dataclass(frozen=True)
class BuildSummary:
    results: dict[str, CompileResult]

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results.values())

    def lines(self) -> list[str]:
        return [
            f"{'ok    ' if r.ok else 'FAILED'} {name}: {len(r.errors)} error(s), {r.pages} page(s), {r.seconds}s"
            for name, r in self.results.items()
        ]


async def build_targets(
    targets: Iterable[Target], compiler: Compiler, *, root: pathlib.Path, outdir: pathlib.Path, jobs: int = 1
) -> BuildSummary:
    """Compile each target into `outdir/<name>`, up to `jobs` at once; the engine comes from the target. Results keep
    declared order."""
    chosen = list(targets)
    slots = asyncio.Semaphore(max(1, jobs))

    async def one(target: Target) -> CompileResult:
        async with slots:
            mine = dataclasses.replace(compiler, engine=get_engine(target.engine))
            plan = load_plan(target.plan, root) if target.plan else None
            return await mine.compile(root / target.source, outdir / target.name, plan=plan)

    async with asyncio.TaskGroup() as group:
        running = [group.create_task(one(t)) for t in chosen]
    return BuildSummary({t.name: r.result() for t, r in zip(chosen, running, strict=True)})


__all__ = ["BuildSummary", "build_targets"]
