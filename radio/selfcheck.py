"""`python3 -m radio --check`: verify code, media and audio before (re)starting the service.

Exits 0 when the radio can run (warnings are allowed), 1 otherwise.
"""
from __future__ import annotations

import importlib

from .audio import EFFECTS
from .stations import MediaError, load_library


def run_check(cfg, open_audio: bool = True) -> int:
    ok = True

    for module in ("radio.app", "radio.audio", "radio.controls", "radio.stations"):
        try:
            importlib.import_module(module)
        except Exception as exc:  # any import failure means a broken checkout
            print(f"FAIL import {module}: {exc}")
            ok = False

    print(f"media: {cfg.media_dir}")
    try:
        library = load_library(cfg.media_dir)
    except MediaError as exc:
        print(f"FAIL media: {exc}")
        return 1
    for station in library.stations:
        ident = "ident" if station.ident else "NO ident"
        print(f"  {station.label:<24} {ident:<9} {len(station.tracks)} track(s)")
    print(f"  welcome: {'yes' if library.welcome else 'MISSING'}")
    for warning in library.warnings:
        print(f"WARN {warning}")

    for name in ("static", *EFFECTS):
        path = cfg.sounds_dir / f"{name}.wav"
        if not path.is_file():
            print(f"FAIL missing sound {path}")
            ok = False

    if open_audio:
        try:
            from .audio import AudioEngine

            engine = AudioEngine(cfg)
            clips = [s.ident for s in library.stations if s.ident] + (
                [library.welcome] if library.welcome else []
            )
            for clip in clips:
                if engine.load_clip(clip) is None:
                    print(f"WARN cannot decode {clip}")
            engine.close()
            print("audio: mixer opened OK")
        except Exception as exc:
            print(f"FAIL audio: {exc}")
            ok = False

    print("CHECK PASSED" if ok else "CHECK FAILED")
    return 0 if ok else 1
