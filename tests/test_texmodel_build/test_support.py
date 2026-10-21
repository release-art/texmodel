import os

import pytest

from texmodel.errors import DeclarationError, ValidationError
from texmodel_build._internal.env import build_env
from texmodel_build.engines import ENGINES, LUALATEX, get_engine
from texmodel_build.roots import resolve, shadowing


def test_env_is_hermetic_and_orders_the_search_path():
    env = build_env(roots=["/r/0", "/r/1"], epoch=1700000000, cache="/cache")
    assert env["TEXINPUTS"] == os.pathsep.join([".", "/r/0", "/r/1"]) + os.pathsep
    assert env["OPENTYPEFONTS"] == "/r/0:/r/1:" and env["TTFONTS"] == env["OPENTYPEFONTS"]
    assert (env["SOURCE_DATE_EPOCH"], env["FORCE_SOURCE_DATE"]) == ("1700000000", "1")
    assert env["TEXMFVAR"] == env["TEXMFCACHE"] == "/cache"
    assert env["max_print_line"] == "10000"  # the log is parsed, so never hard-wrapped


def test_env_without_roots_epoch_or_cache_sets_none_of_them(monkeypatch):
    env = build_env(roots=[])
    assert not {"OPENTYPEFONTS", "TTFONTS", "SOURCE_DATE_EPOCH", "TEXMFVAR"} & env.keys()
    monkeypatch.setenv("TEXMODEL_X", "1")
    assert build_env(roots=[], inherit=["TEXMODEL_X", "TEXMODEL_ABSENT"])["TEXMODEL_X"] == "1"
    assert "TEXMODEL_ABSENT" not in build_env(roots=[], inherit=["TEXMODEL_ABSENT"])


def test_resolve_picks_the_first_root_and_reports_what_it_shadows(tmp_path, caplog):
    a, b = tmp_path / "a", tmp_path / "b"
    for root in (a, b):
        (root / "fonts").mkdir(parents=True)
        (root / "fonts" / "x.otf").write_text(root.name)
    (b / "only-b.sty").write_text("")
    with caplog.at_level("WARNING"):
        hit = resolve("fonts/x.otf", [a, b])
    assert hit and hit.path == a / "fonts" / "x.otf" and hit.shadowed == (b / "fonts" / "x.otf",)
    assert "exists in 2 roots" in caplog.text
    only = resolve("only-b.sty", [a, b])
    assert only and only.shadowed == ()
    assert resolve("nope.sty", [a, b]) is None
    assert [(r.name, r.path.parent.parent.name) for r in shadowing([a, b])] == [("fonts/x.otf", "a")]


@pytest.mark.parametrize("name", ["/etc/passwd", "../x", "a/../../x"])
def test_resolve_refuses_names_that_escape_the_roots(tmp_path, name):
    with pytest.raises(ValidationError) as info:
        resolve(name, [tmp_path])
    assert info.value.code == "TM-C100"


def test_engine_registry():
    assert get_engine("lualatex") is LUALATEX and set(ENGINES) == {"lualatex"}
    with pytest.raises(DeclarationError) as info:
        get_engine("pdftex")
    assert info.value.code == "TM-D010"
