import importlib.metadata
import json
import pathlib

import pytest
from typer.testing import CliRunner

from texmodel import cli, testkit
from texmodel.diagnostics import Severity
from texmodel.errors import ToolchainError
from texmodel.verify import Finding, Profile, exemption, expand_targets, registered, verify_file, verify_files

runner = CliRunner()


class Fake:
    def __init__(self, name="fake", findings=(), why=None, boom=False):
        self.name, self._findings, self._why, self._boom = name, list(findings), why, boom
        self.seen_options: list[object] = []

    def unavailable(self, options):
        self.seen_options.append(options)
        return self._why

    def verify(self, path, options):
        if self._boom:
            raise RuntimeError("kaboom")
        return self._findings


@pytest.fixture
def pdf(tmp_path) -> pathlib.Path:
    path = tmp_path / "a.pdf"
    path.write_bytes(b"%PDF")
    return path


def test_a_clean_verifier_passes_and_receives_its_own_options(pdf):
    v = Fake(findings=[Finding("c", Severity.WARNING, "advisory", page=2)])
    report = verify_file(pdf, Profile(options={"fake": {"x": 1}}), {"fake": v})
    assert report.ok and report.findings[0].page == 2 and v.seen_options == [{"x": 1}]


def test_errors_fail_the_file(pdf):
    report = verify_file(pdf, Profile(), {"v": Fake("v", [Finding("c", Severity.ERROR, "bad")])})
    assert not report.ok and [f.message for f in report.errors] == ["bad"]


def test_unconfirmable_means_failure(pdf, tmp_path):
    avail = {"v": Fake("v", why="no gs")}
    assert [f.message for f in verify_file(pdf, Profile(), avail).errors] == ["cannot confirm: no gs"]
    assert not verify_file(pdf, Profile(), {}).ok  # nothing installed: nothing was checked
    assert not verify_file(pdf, Profile(checks=("nope",)), avail).ok  # unknown verifier
    crashed = verify_file(pdf, Profile(), {"v": Fake("v", boom=True)})
    assert "verifier crashed: RuntimeError('kaboom')" in crashed.errors[0].message
    assert verify_file(tmp_path / "gone.pdf", Profile(), avail).errors[0].check == "open"


def test_exemptions_are_listed_with_their_reason_and_never_fail(pdf):
    report = verify_file(pdf, Profile(), {}, {"*.pdf": "internal docs"})
    assert report.ok and report.exempt == "internal docs" and report.findings == ()


def test_exemption_globs_match_at_any_directory_level():
    p = pathlib.PurePosixPath("job/res/art/x_preview.pdf")
    assert exemption(p, {"*_preview.pdf": "r1"}) == "r1"
    assert exemption(p, {"res/**": "r2"}) == "r2"
    assert exemption(p, {"other/*": "r3"}) is None


def test_verify_files_keeps_order_across_threads(tmp_path):
    files = []
    for i in range(5):
        f = tmp_path / f"{i}.pdf"
        f.write_bytes(b"x")
        files.append(f)
    reports = verify_files(files, Profile(), {"v": Fake("v")}, jobs=3)
    assert [r.path for r in reports] == files


def test_expand_targets(tmp_path):
    (tmp_path / "sub").mkdir()
    for name in ("b.pdf", "a_preview.pdf", "sub/c.pdf", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in expand_targets([tmp_path])] == ["a_preview.pdf", "b.pdf", "c.pdf"]
    assert [p.name for p in expand_targets([tmp_path], exclude=["*_preview.pdf"])] == ["b.pdf", "c.pdf"]
    assert expand_targets([tmp_path / "b.pdf"]) == [tmp_path / "b.pdf"]


def test_entry_points_register_the_builtin_and_a_broken_plugin_is_an_error(monkeypatch):
    assert "proof-pdf" in registered()

    class Bad:
        name = "bad"

        def load(self):
            raise ImportError("nope")

    monkeypatch.setattr(importlib.metadata, "entry_points", lambda group: [Bad()])
    with pytest.raises(ToolchainError) as info:
        registered()
    assert info.value.code == "TM-V001"


def test_the_contract_helper_accepts_a_good_verifier_and_rejects_bad_ones(tmp_path):
    testkit.check_verifier_contract(Fake(), tmp_path)
    testkit.check_verifier_contract(Fake(why="no tool"), tmp_path)
    with pytest.raises(AssertionError):
        testkit.check_verifier_contract(Fake(name=""), tmp_path)
    broken = Fake()
    broken.unavailable = lambda options: 42  # type: ignore[method-assign,assignment,return-value]
    with pytest.raises(AssertionError):
        testkit.check_verifier_contract(broken, tmp_path)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake = Fake("fake", [Finding("c", Severity.ERROR, "bad", page=1)])
    monkeypatch.setattr(cli, "registered", lambda: {"fake": fake})
    (tmp_path / "pyproject.toml").write_text(
        '[tool.texmodel]\nprefix = "t"\n[tool.texmodel.exempt]\n"manual.pdf" = "never printed"\n'
        '[tool.texmodel.profiles.print]\nchecks = ["fake"]\n[tool.texmodel.profiles.print.options.fake]\nx = 1\n'
    )
    (tmp_path / "ok.pdf").write_bytes(b"x")
    (tmp_path / "manual.pdf").write_bytes(b"x")
    return fake


def test_verify_command_reports_failures_and_exemptions(project):
    result = runner.invoke(cli.app, ["verify", "ok.pdf", "manual.pdf", "--profile", "print"])
    assert result.exit_code == 1
    assert "FAILED ok.pdf" in result.stdout and "[c] (page 1) bad" in result.stdout
    assert "exempt  manual.pdf: never printed" in result.stdout
    assert project.seen_options == [{"x": 1}]


def test_verify_command_options_and_json(project):
    result = runner.invoke(
        cli.app,
        ["verify", ".", "--check", "fake", "--exempt", "ok.pdf=because", "--exclude", "x*", "-j", "2", "--json"],
    )
    data = json.loads(result.stdout)
    assert result.exit_code == 0
    by = {pathlib.Path(d["path"]).name: d for d in data}
    assert by["ok.pdf"]["exempt"] == "because" and by["manual.pdf"]["exempt"] == "never printed"


def test_verify_command_with_an_unknown_profile_exits_2(project):
    result = runner.invoke(cli.app, ["verify", "ok.pdf", "--profile", "nope"])
    assert result.exit_code == 2 and "TM-D013" in result.stderr


def test_verify_without_config_runs_every_registered_verifier(project, tmp_path):
    (tmp_path / "pyproject.toml").unlink()
    result = runner.invoke(cli.app, ["verify", "ok.pdf", "--profile", "x"])
    assert result.exit_code == 2
    assert runner.invoke(cli.app, ["verify", "ok.pdf"]).exit_code == 1
