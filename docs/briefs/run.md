# Draft: `texmodel.run`, async

Roadmap section 2, item 0. Status: **built** in texmodel (steps 1 to 4); texpkg (step 5) follows. Decided (2026-10-29): one import root, the engine side named
`texmodel.run`, its code async, one `texmodel` CLI (1), `pytest-asyncio` for the tests (2), texpkg's helpers async with it (3).

## Why

`texmodel_build` is not a build step: it runs the external programs (latexmk with LuaLaTeX, kpsewhich, docker, verapdf
through proof-pdf) and reads what they return. In texpkg, `texpkg_build` *is* the build (code generation a wheel does not
depend on, B8), so the one suffix means two things. A compile takes seconds; a managing system (an MCP server ingesting
hand edits) runs it inside an event loop and must be able to cancel it.

## Layout

```
texmodel/          the core, imports unchanged, never starts a process
texmodel/run/      what was texmodel_build: compiler, targets, testkit, verify, hand_edits, diagnostics, …
texmodel/cli.py    one `texmodel` command: the core's commands, and `texmodel run compile|build|clean|verify|doctor`
```

- `texmodel_build.X` becomes `texmodel.run.X`; `texmodel-build` becomes the `run` group of the `texmodel` script (the
  core already has a `build` command, which writes the `.sty`); the entry-point group
  `texmodel_build.verifiers` becomes `texmodel.run.verifiers`; `[tool.texmodel-build]` becomes `[tool.texmodel.run]`.
- The boundary is an import-linter `layers` contract, `exhaustive = true`, over the `texmodel` container: `cli` above
  `run` above the core modules. Measured with import-linter 2.15 on a scratch package: a core module importing `run`
  breaks it, and so does a new core module not listed in it. It replaces "the core does not know the harness".
- `texmodel/cli.py` is the one module that sees both; only it prints (as today). The two `config` modules stay two:
  the core's and `run`'s.

## Async

What starts a process is `async def`; what reads text stays a plain function.

| Async | Stays sync |
|---|---|
| `Compiler.compile`, `clean`, `versions`, `check_ready`, `missing_files`, `image_info` | `diagnostics`, `logparse`, `fonts.embedded` / `outside` |
| `targets.build_targets` | `CompileResult`, `BuildSummary`, `Versions` |
| `testkit.run_probes`, `check_library`, `check_verifier_contract` | `verify.exemption`, `expand_targets`, `registered` |
| `hand_edits.read_edits` | `engines`, `config` |
| `verify.verify_file`, `verify_files`, `Verifier.verify` | `Verifier.unavailable` |

- `_internal/spawn.py` uses `asyncio.create_subprocess_exec` (argv only, as now); the timeout is `asyncio.timeout`. On a
  timeout **or a cancellation** the child is killed and awaited, and a docker run gets `docker kill` as today, so a
  cancelled compile leaves no container behind. import-linter forbids `subprocess` everywhere; a test
  keeps `create_subprocess_*` in `spawn` (import-linter cannot see an attribute call).
- `build_targets` and `verify_files` run their `jobs` in an `asyncio.TaskGroup` under a `Semaphore(jobs)`, not a thread
  pool; results keep the declared order, as now.
- `Verifier.verify` is async: proof-pdf's `verify_file` is a coroutine already, so its adapter awaits it and the
  `asyncio.run` per file (and its `ponytail:` note: not callable inside a running loop) goes.
- No sync twins: one way to call each. The CLI calls `asyncio.run` once per command; a sync caller (texpkg's tests, its
  `testing` helpers) does the same.

## Tests

- The existing compile and probe tests, awaited. `pytest-asyncio` as a dev dependency with
  `asyncio_mode = "auto"`, so a test is `async def` and awaits; fixtures stay as they are.
- New: a timed-out and a cancelled compile kill the child and, in the image, the container (`tex`); `jobs=2` builds two
  targets at once (the wall time of the slower, not the sum, with a stub spawn); the import contract fails on a core
  module that imports `texmodel.run` (a scratch package, as measured).

## Decisions (taken 2026-10-29)

1. **The CLI.** One `texmodel` command; `texmodel-build` goes, its commands as they are under `texmodel run`.
2. **The async test runner.** `pytest-asyncio` (dev only), not `asyncio.run(...)` at each of ~80 call sites.
3. **texpkg.** `texpkg_build.testing` turns async with it (its helpers compile), released together; texpkg's
   own name `texpkg_build` stays, as it is the build.

## Steps

1. Move `texmodel_build` to `texmodel/run/`, the contract, the one CLI (no behaviour change; output unchanged).
2. `spawn` async with kill on timeout and cancellation; everything above it awaited; the task groups.
3. `Verifier.verify` async, proof-pdf's adapter.
4. Guide (every page naming `texmodel_build` or `texmodel-build`), README, AGENTS.md, known limitations, the plan's
   decisions log, changelog (`Changed`: the import path, the CLI, the config table, async).
5. texpkg, after the texmodel release (it installs texmodel from PyPI, so it cannot import `texmodel.run` before):
   `texmodel>=` the release; imports; `check_isolated` and the compile tests async (`pytest-asyncio`); its changelog.
   Its contract "the run time imports only the standard library, texmodel and pydantic" forbids `texmodel_build`, and
   import-linter refuses a subpackage of an external package (`texmodel.run`: measured, 2.15), so texpkg lists
   `texmodel` among its `root_packages` to forbid `texmodel.run`.
