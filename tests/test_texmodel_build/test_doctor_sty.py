"""`texmodel-build doctor --sty` (D2): which files a package loads are missing from the toolchain."""

import json
import shutil

import pytest
from typer.testing import CliRunner

from texmodel.errors import DeclarationError
from texmodel_build import cli
from texmodel_build._internal.styscan import needed
from texmodel_build.compiler import Compiler

runner = CliRunner()

STY = r"""
\NeedsTeXFormat{LaTeX2e}
\ProvidesPackage{kit}
\RequirePackage[table,dvipsnames]{xcolor}   % colours
\RequirePackage{enumitem, hyphenat}
\usepackage{tikz}
\RequirePackageWithOptions{geometry}
% \RequirePackage{commented}
\LoadClass[11pt]{article}
\tcbuselibrary{skins,breakable}
\RequirePackage{\kitdep}
\RequirePackage{kit-extra}
50\% \RequirePackage{after-percent}
"""


def test_the_files_a_package_loads_are_read_in_order_once_and_names_from_macros_are_unchecked():
    files, unchecked = needed([STY, r"\RequirePackage{xcolor}"])
    assert files == [
        "xcolor.sty",
        "enumitem.sty",
        "hyphenat.sty",
        "tikz.sty",
        "geometry.sty",
        "article.cls",
        "tcblibraryskins.code.tex",
        "tcblibrarybreakable.code.tex",
        "kit-extra.sty",
        "after-percent.sty",
    ]
    assert unchecked == ["\\kitdep"]
    assert needed([r"\RequirePackage{a,, ,b}"]) == (["a.sty", "b.sty"], [])  # empty names are no names


@pytest.fixture
def project(tmp_path, monkeypatch, toolchain):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[tool.texmodel-build]\nimage = "img:1"\n')
    (tmp_path / "res").mkdir()
    (tmp_path / "res" / "kit.sty").write_text(STY)
    (tmp_path / "res" / "kit-extra.sty").write_text(r"\RequirePackage{kit}\RequirePackage{xcolor}")
    return tmp_path


def test_missing_files_are_named_with_the_tlmgr_line_and_exit_3(project, toolchain):
    toolchain.missing_files = {"hyphenat.sty", "enumitem.sty", "article.cls"}
    result = runner.invoke(cli.app, ["doctor", "--sty", "res/*.sty"])
    assert result.exit_code == 3
    assert "missing enumitem.sty" in result.stdout and "missing article.cls" in result.stdout
    assert (
        "install: tlmgr install enumitem hyphenat" in result.stdout and "tlmgr search --global --file" in result.stdout
    )
    assert "unchecked \\kitdep" in result.stdout
    assert "kit-extra" not in result.stdout  # a sibling of the scanned files is theirs, not the toolchain's


def test_nothing_missing_is_ok_and_json_carries_the_report(project, toolchain):
    ok = runner.invoke(cli.app, ["doctor", "--sty", "res/kit.sty"])
    assert ok.exit_code == 0 and "ok: the 10 file(s) loaded by 1 scanned file(s) are found" in ok.stdout
    data = json.loads(runner.invoke(cli.app, ["doctor", "--json", "--sty", "res/*.sty", "--sty", "res/kit.sty"]).stdout)
    assert data["sty"]["missing"] == [] and data["sty"]["scanned"] == ["res/kit-extra.sty", "res/kit.sty"]
    toolchain.missing_files = {"article.cls"}
    only_class = runner.invoke(cli.app, ["doctor", "--sty", "res/*.sty"])
    assert "install: see tlmgr search --file" in only_class.stdout


def test_no_matching_file_and_no_kpsewhich_are_refused(project, toolchain):
    nothing = runner.invoke(cli.app, ["doctor", "--sty", "nope/*.sty"])
    assert nothing.exit_code == 2 and "TM-D014" in nothing.stderr
    toolchain.no_kpsewhich = True
    gone = runner.invoke(cli.app, ["doctor", "--sty", "res/*.sty"])
    assert gone.exit_code == 3 and "kpsewhich is not installed" in gone.stderr


def test_on_this_machine_without_an_image_and_with_a_broken_image_the_scan_is_skipped(project, toolchain, monkeypatch):
    (project / "pyproject.toml").write_text("[tool.texmodel-build]\n")
    monkeypatch.setattr(shutil, "which", lambda name: f"/bin/{name}")
    toolchain.missing_files = {"tikz.sty"}
    assert "missing tikz.sty" in runner.invoke(cli.app, ["doctor", "--sty", "res/*.sty"]).stdout
    (project / "pyproject.toml").write_text('[tool.texmodel-build]\nimage = "img:1"\n')
    toolchain.image_missing = True
    broken = runner.invoke(cli.app, ["doctor", "--sty", "res/*.sty"])
    assert broken.exit_code == 3 and "missing " not in broken.stdout.replace("missing  ", "")


def test_a_file_name_that_is_not_plain_is_refused_before_it_reaches_a_shell():
    with pytest.raises(DeclarationError, check=lambda e: e.code == "TM-T006"):
        Compiler().missing_files(["a.sty; rm -rf x"])
    assert Compiler().missing_files([]) == ()
