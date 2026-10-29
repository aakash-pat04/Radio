#!/usr/bin/env python3
"""Generate the radio's built-in sounds (pure Python, no numpy).

    python3 tools/make_sounds.py                      # assets/sounds/*.wav
    python3 tools/make_sounds.py --tones media-example  # placeholder station tracks

Output is deterministic (fixed seed), so re-running gives identical files.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import wave
from array import array
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RATE = 44100


def write_wav(path: Path, samples: list[float], rate: int = RATE, stereo: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = array("h")
    for s in samples:
        v = int(max(-1.0, min(1.0, s)) * 32767)
        pcm.append(v)
        if stereo:
            pcm.append(v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2 if stereo else 1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def static(seconds: float = 1.5) -> list[float]:
    """AM-radio style hiss with a slow wobble, crackles and a faint whistle. Loops cleanly."""
    rng = random.Random(5)
    n = int(seconds * RATE)
    out = []
    low = 0.0
    for i in range(n):
        t = i / n
        white = rng.uniform(-1, 1)
        low += 0.35 * (white - low)  # soften the top end
        wobble = 0.75 + 0.25 * math.sin(2 * math.pi * 3 * t)  # 3 cycles per loop
        crackle = rng.uniform(-1, 1) * 0.9 if rng.random() < 0.0008 else 0.0
        whistle = 0.06 * math.sin(math.pi * t) ** 2 * math.sin(
            2 * math.pi * (900 + 500 * t) * i / RATE
        )
        out.append(0.55 * low * wobble + crackle + whistle)
    return out


def tone(freqs: list[float], seconds: float, decay: float, gain: float = 0.5) -> list[float]:
    out = []
    for i in range(int(seconds * RATE)):
        t = i / RATE
        env = min(1.0, t / 0.005) * math.exp(-t / decay)
        out.append(gain * env * sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs))
    return out


def notes(sequence: list[tuple[float, float]], decay: float = 0.35) -> list[float]:
    out: list[float] = []
    for freq, length in sequence:
        out += tone([freq, freq * 2], length, decay)
    return out


def effects() -> dict[str, list[float]]:
    return {
        "static": static(),
        "tick": tone([2200], 0.04, 0.01, 0.4),
        "blip": tone([880], 0.07, 0.03, 0.4),
        "home": notes([(659.25, 0.18), (880.0, 0.5)]),
        "goodbye": notes([(880.0, 0.25), (659.25, 0.25), (523.25, 0.9)], decay=0.5),
    }


def placeholder_track(root: float, seconds: float = 8.0, rate: int = 22050) -> list[float]:
    """A gentle arpeggio so the play/pause path is testable without real music."""
    steps = [1.0, 1.25, 1.5, 2.0, 1.5, 1.25]
    note_len = 0.5
    out = []
    for i in range(int(seconds * rate)):
        t = i / rate
        f = root * steps[int(t / note_len) % len(steps)]
        local = t % note_len
        env = min(1.0, local / 0.01) * math.exp(-local / 0.3)
        fade = min(1.0, t / 0.5, (seconds - t) / 0.5)
        out.append(0.3 * env * fade * math.sin(2 * math.pi * f * t))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tones", metavar="MEDIA_DIR", help="write placeholder tracks into each station folder")
    args = parser.parse_args()

    if args.tones:
        media = Path(args.tones)
        stations = json.loads((media / "stations.json").read_text())["stations"]
        for number, station in enumerate(stations):
            path = media / station["folder"] / "01-placeholder-tone.wav"
            write_wav(path, placeholder_track(220 * 2 ** (number / 6)), rate=22050, stereo=False)
            print(f"wrote {path}")
        return

    for name, samples in effects().items():
        path = REPO / "assets" / "sounds" / f"{name}.wav"
        write_wav(path, samples)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
