"""Settings for Five Years FM.

Every field has a sensible default. On the Pi, override them in
/etc/default/radio (read by radio.service) so they survive code updates.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_MEDIA = REPO_ROOT / "media-example"


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


def default_media_dir() -> Path:
    """RADIO_MEDIA if set, else ~/radio-media if it has stations, else the bundled example."""
    env = os.environ.get("RADIO_MEDIA")
    if env:
        return Path(env).expanduser()
    personal = Path.home() / "radio-media"
    if (personal / "stations.json").exists():
        return personal
    return EXAMPLE_MEDIA


@dataclass
class Config:
    media_dir: Path
    sounds_dir: Path = REPO_ROOT / "assets" / "sounds"
    state_file: Path = Path.home() / ".local" / "state" / "radio" / "state.json"

    # Encoder wiring, BCM numbering (physical pins 29, 31, 33).
    pin_clk: int = 5
    pin_dt: int = 6
    pin_sw: int = 13
    # Quadrature transitions per detent click: 4 for most KY-040s, 2 for half-step ones.
    transitions_per_detent: int = 4
    reverse_rotation: bool = False
    button_bounce_s: float = 0.03

    # Gesture timings.
    tune_settle_s: float = 0.6
    long_press_s: float = 1.5
    shutdown_hold_s: float = 8.0

    # Audio.
    sample_rate: int = 44100
    buffer_frames: int = 2048
    default_volume: float = 0.7
    volume_step: float = 0.05
    static_gain: float = 0.35
    effect_gain: float = 0.6

    # Dial behaviour.
    wrap_dial: bool = True
    autoplay: bool = False

    @classmethod
    def from_env(cls, media: str | Path | None = None) -> "Config":
        cfg = cls(media_dir=Path(media).expanduser() if media else default_media_dir())
        state = os.environ.get("RADIO_STATE")
        if state:
            cfg.state_file = Path(state).expanduser()
        cfg.pin_clk = _env_int("RADIO_PIN_CLK", cfg.pin_clk)
        cfg.pin_dt = _env_int("RADIO_PIN_DT", cfg.pin_dt)
        cfg.pin_sw = _env_int("RADIO_PIN_SW", cfg.pin_sw)
        cfg.transitions_per_detent = _env_int(
            "RADIO_TRANSITIONS_PER_DETENT", cfg.transitions_per_detent
        )
        if cfg.transitions_per_detent not in (2, 4):
            raise ValueError("RADIO_TRANSITIONS_PER_DETENT must be 2 or 4")
        cfg.reverse_rotation = _env_bool("RADIO_REVERSE", cfg.reverse_rotation)
        cfg.tune_settle_s = _env_float("RADIO_TUNE_SETTLE_S", cfg.tune_settle_s)
        cfg.long_press_s = _env_float("RADIO_LONG_PRESS_S", cfg.long_press_s)
        cfg.shutdown_hold_s = _env_float("RADIO_SHUTDOWN_HOLD_S", cfg.shutdown_hold_s)
        cfg.default_volume = _env_float("RADIO_DEFAULT_VOLUME", cfg.default_volume)
        cfg.buffer_frames = _env_int("RADIO_BUFFER_FRAMES", cfg.buffer_frames)
        cfg.wrap_dial = _env_bool("RADIO_WRAP_DIAL", cfg.wrap_dial)
        cfg.autoplay = _env_bool("RADIO_AUTOPLAY", cfg.autoplay)
        return cfg
