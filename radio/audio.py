"""Audio output through pygame.mixer only; no window or display is opened.

Channels:
    music  pygame.mixer.music  streams the station playlist
    0      static              tuning noise / dead air, looped
    1      voice               idents and the welcome clip
    2      effects             tick, chimes, volume blip
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

EFFECTS = ("tick", "home", "goodbye", "blip")


class AudioEngine:
    def __init__(self, cfg):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        if sys.platform.startswith("linux"):
            os.environ.setdefault("SDL_AUDIODRIVER", "alsa")
        import pygame

        self._pg = pygame
        self._cfg = cfg
        pygame.mixer.pre_init(cfg.sample_rate, -16, 2, cfg.buffer_frames)
        pygame.mixer.init()
        pygame.mixer.set_num_channels(4)
        self._static_ch = pygame.mixer.Channel(0)
        self._voice_ch = pygame.mixer.Channel(1)
        self._effect_ch = pygame.mixer.Channel(2)
        self._clips: dict[Path, object] = {}
        self._static = self._load(cfg.sounds_dir / "static.wav")
        self._effects = {name: self._load(cfg.sounds_dir / f"{name}.wav") for name in EFFECTS}
        self._volume = cfg.default_volume
        self._static_quiet = False
        self._static_on = False
        self.set_volume(cfg.default_volume)

    def _load(self, path: Path):
        try:
            return self._pg.mixer.Sound(str(path))
        except (self._pg.error, FileNotFoundError) as exc:
            log.warning("could not load %s: %s", path, exc)
            return None

    # Volume -------------------------------------------------------------

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        self._pg.mixer.music.set_volume(self._volume)
        self._apply_static_volume()
        for sound in self._effects.values():
            if sound is not None:
                sound.set_volume(self._volume * self._cfg.effect_gain)
        for sound in self._clips.values():
            sound.set_volume(self._volume)

    def _apply_static_volume(self) -> None:
        if self._static is not None:
            gain = self._cfg.static_gain * (0.4 if self._static_quiet else 1.0)
            self._static.set_volume(self._volume * gain)

    # Static -------------------------------------------------------------

    def play_static(self, quiet: bool = False) -> None:
        if self._static is None:
            return
        self._static_quiet = quiet
        self._apply_static_volume()
        # Restart unless already looping; a fade-out in progress counts as stopped.
        if not (self._static_on and self._static_ch.get_busy()):
            self._static_ch.play(self._static, loops=-1, fade_ms=60)
        self._static_on = True

    def stop_static(self, fade_ms: int = 250) -> None:
        self._static_on = False
        if fade_ms:
            self._static_ch.fadeout(fade_ms)
        else:
            self._static_ch.stop()

    # Voice clips (idents, welcome) ----------------------------------------

    def load_clip(self, path: Path):
        sound = self._clips.get(path)
        if sound is None:
            sound = self._load(path)
            if sound is not None:
                sound.set_volume(self._volume)
                self._clips[path] = sound
        return sound

    def play_clip(self, path: Path) -> bool:
        sound = self.load_clip(path)
        if sound is None:
            return False
        self._voice_ch.play(sound)
        return True

    def clip_busy(self) -> bool:
        return self._voice_ch.get_busy()

    def stop_clip(self) -> None:
        self._voice_ch.stop()

    # Effects ------------------------------------------------------------

    def play_effect(self, name: str) -> None:
        sound = self._effects.get(name)
        if sound is not None:
            self._effect_ch.play(sound)

    def effect_busy(self) -> bool:
        return self._effect_ch.get_busy()

    # Station playlist ---------------------------------------------------

    def play_track(self, path: Path) -> bool:
        music = self._pg.mixer.music
        try:
            music.load(str(path))
            music.play()
        except self._pg.error as exc:
            log.warning("could not play %s: %s", path, exc)
            return False
        log.info("playing %s", path.name)
        return True

    def music_busy(self) -> bool:
        return self._pg.mixer.music.get_busy()

    def pause(self) -> None:
        self._pg.mixer.music.pause()

    def resume(self) -> None:
        self._pg.mixer.music.unpause()

    def stop_music(self) -> None:
        self._pg.mixer.music.stop()

    def stop_all(self) -> None:
        self.stop_music()
        self.stop_clip()
        self.stop_static(fade_ms=0)
        self._effect_ch.stop()

    def close(self) -> None:
        self._pg.mixer.quit()
