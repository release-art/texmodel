import pathlib
import re

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
    (note,) = d.notes
    assert note.startswith("gen/edited.sty: generated with texmodel 0.1.0, current is 0.2.0; no release since 0.1.0")
    assert not d.ok


@pytest.mark.parametrize(
    ("written", "current", "body", "why"),
    [
        ("0.9.0", "0.10.0", "same", "only the version line differs"),
        (
            "0.9.0",
            "0.10.0",
            "old",
            r"output changed in 0.10.0 (`ext.fit` declares its two public lengths with `\newlength`)",
        ),
        ("0.7.0", "0.10.0", "old", "output changed in 0.8.0 (a document's"),
        ("0.10.0", "0.10.1", "old", "no release since 0.10.0 changed generated output"),
        ("dev", "0.10.0", "old", "its version cannot be compared"),
    ],
)
def test_a_note_says_what_the_upgrade_explains_of_a_stale_file(tmp_path, written, current, body, why):
    """K3, G7: the releases between the two versions that changed output, or that none did, so a hand edit or a change
    to the declarations is not taken for the upgrade."""
    (tmp_path / "a.sty").write_text(f"% {drift.stamp(written)}\n{body}")
    (note,) = drift.check_drift({"a.sty": f"% {drift.stamp(current)}\nsame"}, tmp_path, version=current).notes
    assert note.startswith(f"a.sty: generated with texmodel {written}, current is {current}; {why}")
    assert note.endswith(": run `texmodel build`")


def test_every_output_change_is_marked_in_the_changelog_and_listed_in_the_table():
    """A release that changes output says so on one line of its changelog section, `Output change: <text>.`, and
    `OUTPUT_CHANGES` carries the same text, so the installed `check` can name it (G7, K3)."""
    changelog = (pathlib.Path(__file__).parents[2] / "CHANGELOG.md").read_text(encoding="utf-8")
    marked: dict[str, str] = {}
    for section in re.split(r"^## ", changelog, flags=re.MULTILINE):
        release = re.match(r"\[(\d+\.\d+\.\d+)\]", section)
        line = re.search(r"^Output change: (.+)\.$", section, flags=re.MULTILINE)
        if release and line:
            marked[release[1]] = line[1]
    assert marked == dict(drift.OUTPUT_CHANGES)


def test_drift_ok_when_everything_matches(tmp_path):
    (tmp_path / "a.sty").write_text("A")
    d = drift.check_drift({"a.sty": "A"}, tmp_path)
    assert d.ok and d == drift.Drift()
