import os

import pytest

from texmodel.errors import DeclarationError
from texmodel_build._internal.env import build_env
from texmodel_build.engines import ENGINES, LUALATEX, get_engine


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


def test_engine_registry():
    assert get_engine("lualatex") is LUALATEX and set(ENGINES) == {"lualatex"}
    with pytest.raises(DeclarationError) as info:
        get_engine("pdftex")
    assert info.value.code == "TM-D010"
