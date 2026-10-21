import pathlib

import pytest

from texmodel import drift
from texmodel.bundle import Item, missing, stale, write
from texmodel.errors import DeclarationError


@pytest.fixture
def items(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.sty").write_text("A")
    (src / "Face.ttf").write_bytes(b"\0font")
    return [
        Item(src / "a.sty", pathlib.Path("res/brand/a.sty"), "the package"),
        Item(src / "Face.ttf", pathlib.Path("Face.ttf"), "the face"),
    ]


def test_write_copies_bytes_and_generated_files(items, tmp_path):
    out = tmp_path / "bundle"
    written = write(items, out, {"README.md": "hello"})
    assert {p.relative_to(out).as_posix() for p in written} == {"res/brand/a.sty", "Face.ttf", "README.md"}
    assert (out / "Face.ttf").read_bytes() == b"\0font" and (out / "README.md").read_text() == "hello"


def test_write_refuses_everything_when_a_source_is_missing(items, tmp_path):
    items[1].source.unlink()
    assert missing(items) == (items[1],)
    with pytest.raises(DeclarationError) as info:
        write(items, tmp_path / "bundle")
    assert info.value.code == "TM-B001" and "Face.ttf" in str(info.value)
    assert not (tmp_path / "bundle").exists()


def test_destinations_cannot_escape(items, tmp_path):
    for bad in (pathlib.Path("../x"), pathlib.Path("/abs/x")):
        with pytest.raises(DeclarationError) as info:
            write([Item(items[0].source, bad)], tmp_path / "b")
        assert info.value.code == "TM-B002"
    with pytest.raises(DeclarationError):
        write([], tmp_path / "b", {"../evil": "x"})


def test_stale_compares_content_not_timestamps(items, tmp_path):
    out = tmp_path / "t"
    assert stale(items, out) == tuple(items)
    write(items, out)
    assert stale(items, out) == ()
    (out / "Face.ttf").write_bytes(b"other")
    assert stale(items, out) == (items[1],)


def test_drift_reports_stale_missing_orphaned_and_old_versions(tmp_path):
    (tmp_path / "gen").mkdir()
    (tmp_path / "gen" / "ok.sty").write_text("same")
    (tmp_path / "gen" / "edited.sty").write_text(f"% {drift.stamp('0.1.0')}\nhand edit")
    (tmp_path / "gen" / "extra.sty").write_text("nobody generates me")
    (tmp_path / "keep.txt").write_text("not owned")
    expected = {"gen/ok.sty": "same", "gen/edited.sty": f"% {drift.stamp('0.2.0')}\nfresh", "gen/gone.sty": b"x"}
    d = drift.check_drift(expected, tmp_path, owned=("gen/*",), version="0.2.0")
    assert (d.stale, d.missing, d.orphaned) == (("gen/edited.sty",), ("gen/gone.sty",), ("gen/extra.sty",))
    assert d.notes == ("gen/edited.sty: generated with texmodel 0.1.0, current is 0.2.0: run `texmodel build`",)
    assert not d.ok


def test_drift_ok_when_everything_matches(tmp_path):
    (tmp_path / "a.sty").write_text("A")
    d = drift.check_drift({"a.sty": "A"}, tmp_path)
    assert d.ok and d == drift.Drift()
