import json

import pytest

from radio.config import EXAMPLE_MEDIA
from radio.stations import MediaError, load_library


def write_index(root, stations):
    (root / "stations.json").write_text(json.dumps({"stations": stations}))


def test_example_media_is_complete():
    library = load_library(EXAMPLE_MEDIA)
    assert [s.label for s in library.stations] == [
        "88.1 First Signal",
        "90.5 Year One",
        "92.7 Our Best Days",
        "95.3 Little Things FM",
        "98.9 The Love Letter",
        "100.0 Future Frequency",
    ]
    assert library.welcome is not None
    assert library.warnings == []
    assert all(s.ident and s.tracks for s in library.stations)


def test_tracks_sorted_and_ident_excluded(tmp_path):
    folder = tmp_path / "a"
    folder.mkdir()
    for name in ("ident.ogg", "02-b.mp3", "01-a.OGG", "notes.txt", ".hidden.ogg"):
        (folder / name).write_bytes(b"")
    write_index(tmp_path, [{"freq": "88.1", "name": "A", "folder": "a"}])
    station = load_library(tmp_path).stations[0]
    assert station.ident.name == "ident.ogg"
    assert [t.name for t in station.tracks] == ["01-a.OGG", "02-b.mp3"]


def test_missing_pieces_are_warnings(tmp_path):
    (tmp_path / "empty").mkdir()
    write_index(
        tmp_path,
        [
            {"freq": "88.1", "name": "Gone", "folder": "gone"},
            {"freq": "90.5", "name": "Empty", "folder": "empty"},
        ],
    )
    library = load_library(tmp_path)
    assert len(library.stations) == 2
    text = "\n".join(library.warnings)
    assert "Gone: folder" in text
    assert "Empty: no ident" in text
    assert "Empty: no audio tracks" in text
    assert "welcome" in text


@pytest.mark.parametrize(
    "content",
    ["not json", "{}", '{"stations": []}', '{"stations": [{"freq": "88.1"}]}'],
)
def test_bad_index_raises(tmp_path, content):
    (tmp_path / "stations.json").write_text(content)
    with pytest.raises(MediaError):
        load_library(tmp_path)


def test_missing_index_raises(tmp_path):
    with pytest.raises(MediaError):
        load_library(tmp_path)
