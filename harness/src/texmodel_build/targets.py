"""Build every declared target (C10): reruns until stable are the compiler's, this adds parallelism and one summary."""

import dataclasses
import pathlib
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

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


def build_targets(
    targets: Iterable[Target], compiler: Compiler, *, root: pathlib.Path, outdir: pathlib.Path, jobs: int = 1
) -> BuildSummary:
    """Compile each target into `outdir/<name>`; the engine comes from the target. Results keep declared order."""
    chosen = list(targets)

    def one(target: Target) -> CompileResult:
        mine = dataclasses.replace(compiler, engine=get_engine(target.engine))
        plan = load_plan(target.plan, root) if target.plan else None
        return mine.compile(root / target.source, outdir / target.name, plan=plan)

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return BuildSummary({t.name: r for t, r in zip(chosen, pool.map(one, chosen), strict=True)})
