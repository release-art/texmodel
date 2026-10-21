"""A fake toolchain behind `driver._spawn`, so the driver's branches run without Docker or TeX."""

import pathlib
import re

import pytest

from texmodel import compiler
from texmodel._internal.spawn import Proc

driver_proc = Proc

PROBE_OK = (
    "Latexmk, John Collins, 15 June 2025. Version 4.87\n@@\n"
    "This is LuaHBTeX, Version 1.22.0 (TeX Live 2025)\n@@\nkpsewhich\ngs\n"
)
OK_LOG = "(./a.tex)\nOutput written on a.pdf (1 page, 100 bytes).\n"


class FakeToolchain:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.probe = PROBE_OK
        self.inspect = ("sha256:" + "ab" * 32, "deadbeefcafe")
        self.log = OK_LOG
        self.returncode = 0
        self.stdout = "Run number 1 of rule 'pdflatex'\n"
        self.write_pdf = True
        self.timed_out = False
        self.image_missing = False
        self.latexmk_returncode: int | None = None  # overrides returncode for the clean call
        self.runs = 0
        self.up_to_date = True  # like latexmk: outputs already current in the outdir mean no pass runs

    def __call__(self, argv, *, cwd, env, timeout):  # noqa: ANN001, ANN204
        argv = list(argv)
        self.calls.append(argv)
        if argv[:3] == ["docker", "image", "inspect"]:
            if self.image_missing:
                return Proc(1, "", "Error: No such image")
            return Proc(0, "|".join(self.inspect) + "\n", "")
        if argv[:2] == ["docker", "kill"]:
            return Proc(0, "", "")
        if "sh" in argv and "-c" in argv:
            return Proc(0, self.probe, "")
        if "-c" in argv or "-C" in argv:  # latexmk -c / -C (clean)
            return Proc(self.latexmk_returncode or 0, "", "")
        out = self._outdir(argv)
        stem = pathlib.Path(argv[-1]).stem
        pdf_there = (out / f"{stem}.pdf").is_file() and (out / f"{stem}.log").is_file()
        if self.up_to_date and pdf_there and self.log is not None and self.write_pdf and self.returncode == 0:
            return driver_proc(0, f"Latexmk: All targets ({out / (stem + '.pdf')}) are up-to-date\n", "")
        self.runs += 1
        if self.timed_out:
            return Proc(-1, "partial", "", timed_out=True)
        if self.log is not None:
            (out / f"{stem}.log").write_text(self.log)
            (out / f"{stem}.aux").write_text(f"\\newlabel{{k}}{{{{{self.runs}}}{{1}}}}\n")
        if self.write_pdf:
            (out / f"{stem}.pdf").write_bytes(b"%PDF-fake")
        return Proc(self.returncode, self.stdout, "")

    def _outdir(self, argv: list[str]) -> pathlib.Path:
        if argv[0] == "docker":  # the host directory mounted at /work/out
            mount = next(a for a in argv if a.startswith("type=bind") and "target=/work/out" in a)
            return pathlib.Path(re.search(r"source=([^,]+)", mount)[1])  # type: ignore[index]
        return pathlib.Path(next(a for a in argv if a.startswith("-outdir="))[len("-outdir=") :])


@pytest.fixture
def toolchain(monkeypatch: pytest.MonkeyPatch) -> FakeToolchain:
    fake = FakeToolchain()
    monkeypatch.setattr(compiler, "spawn", fake)
    return fake
