"""Load the station list and audio files from the media folder.

Layout:
    stations.json            {"stations": [{"freq": "88.1", "name": "First Signal",
                                            "folder": "88.1-first-signal"}, ...]}
    home/welcome.ogg         played at boot and on a short press at home
    <folder>/ident.ogg       station announcement played after tuning
    <folder>/*.ogg|mp3|wav   the station's playlist, in filename order
    <folder>/memory.txt, photos/   kept for the screen revision; ignored here
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

AUDIO_EXTS = (".ogg", ".mp3", ".wav")


class MediaError(Exception):
    """The media folder is unusable (missing or malformed stations.json)."""


@dataclass
class Station:
    freq: str
    name: str
    folder: Path
    ident: Path | None
    tracks: list[Path]

    @property
    def label(self) -> str:
        return f"{self.freq} {self.name}"


@dataclass
class Library:
    root: Path
    stations: list[Station]
    welcome: Path | None
    warnings: list[str] = field(default_factory=list)


def find_audio(folder: Path, stem: str) -> Path | None:
    for ext in AUDIO_EXTS:
        candidate = folder / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def _tracks(folder: Path) -> list[Path]:
    return sorted(
        (
            p
            for p in folder.iterdir()
            if p.is_file()
            and p.suffix.lower() in AUDIO_EXTS
            and p.stem.lower() != "ident"
            and not p.name.startswith(".")
        ),
        key=lambda p: p.name.lower(),
    )


def load_library(media_dir: Path) -> Library:
    index = media_dir / "stations.json"
    if not index.is_file():
        raise MediaError(f"{index} not found")
    try:
        data = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MediaError(f"{index} is not valid JSON: {exc}") from exc

    entries = data.get("stations") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise MediaError(f'{index} needs a non-empty "stations" list')

    warnings: list[str] = []
    stations: list[Station] = []
    for number, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(key), str) and entry[key].strip()
            for key in ("freq", "name", "folder")
        ):
            raise MediaError(
                f'{index} station {number} needs "freq", "name" and "folder" strings'
            )
        folder = media_dir / entry["folder"]
        label = f'{entry["freq"]} {entry["name"]}'
        if folder.is_dir():
            ident = find_audio(folder, "ident")
            tracks = _tracks(folder)
        else:
            warnings.append(f"{label}: folder {folder} is missing")
            ident, tracks = None, []
        if folder.is_dir() and ident is None:
            warnings.append(f"{label}: no ident.ogg/mp3/wav")
        if folder.is_dir() and not tracks:
            warnings.append(f"{label}: no audio tracks (will play soft static)")
        stations.append(Station(entry["freq"], entry["name"], folder, ident, tracks))

    welcome = find_audio(media_dir / "home", "welcome")
    if welcome is None:
        warnings.append("home/welcome.ogg/mp3/wav is missing")

    return Library(media_dir, stations, welcome, warnings)
