"""The radio's state machine.

HOME --turn--> TUNING --settle--> TUNED --press--> PLAYING <--press--> PAUSED
Any state --long press--> HOME;  any state --8 s hold--> SHUTDOWN
"""
from __future__ import annotations

import enum
import json
import logging
import os
import queue
import time
from pathlib import Path
from typing import Callable

from .controls import Event
from .stations import Library

log = logging.getLogger(__name__)

TRACK_START_GRACE_S = 0.5
SAVE_DELAY_S = 2.0
SHUTDOWN_CHIME_TIMEOUT_S = 4.0


class State(enum.Enum):
    HOME = "home"
    TUNING = "tuning"
    TUNED = "tuned"
    PLAYING = "playing"
    PAUSED = "paused"
    SHUTDOWN = "shutdown"


class StateStore:
    """Remembers the last station and volume across reboots."""

    def __init__(self, path: Path):
        self._path = path

    def load(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, data: dict) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, self._path)
        except OSError as exc:
            log.warning("could not save state: %s", exc)


class App:
    def __init__(
        self,
        cfg,
        library: Library,
        audio,
        controls,
        events: "queue.Queue[Event]",
        store: StateStore | None = None,
        poweroff: Callable[[], None] = lambda: None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.cfg = cfg
        self.library = library
        self.audio = audio
        self.controls = controls
        self.events = events
        self.store = store
        self.poweroff = poweroff
        self.clock = clock

        saved = store.load() if store else {}
        count = len(library.stations)
        self.index = saved.get("station", 0) if isinstance(saved.get("station"), int) else 0
        self.index = min(max(self.index, 0), count - 1)
        volume = saved.get("volume", cfg.default_volume)
        self.volume = min(max(float(volume), 0.0), 1.0) if isinstance(volume, (int, float)) else cfg.default_volume

        self.state = State.HOME
        self.running = True
        self._settle_at = 0.0
        self._autoplay_pending = False
        self._track_pos: dict[int, int] = {}
        self._track_started = 0.0
        self._empty_station = False
        self._shutdown_at = 0.0
        self._save_at: float | None = None

    @property
    def station(self):
        return self.library.stations[self.index]

    # Lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self.audio.set_volume(self.volume)
        if self.library.welcome:
            self.audio.play_clip(self.library.welcome)
        log.info("ready: %d stations, at home", len(self.library.stations))

    def run(self, tick_s: float = 0.05) -> None:
        self.start()
        while self.running:
            self.step()
            time.sleep(tick_s)
        self._flush_save()

    def step(self) -> None:
        self.controls.poll()
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            self.handle(event)

        now = self.clock()
        if self.state is State.TUNING and now >= self._settle_at:
            self._finish_tuning()
        elif self.state is State.TUNED and self._autoplay_pending and not self.audio.clip_busy():
            self._autoplay_pending = False
            self._start_station()
        elif self.state is State.PLAYING and not self._empty_station:
            if now - self._track_started > TRACK_START_GRACE_S and not self.audio.music_busy():
                self._advance_track()
        elif self.state is State.SHUTDOWN:
            if not self.audio.effect_busy() or now - self._shutdown_at > SHUTDOWN_CHIME_TIMEOUT_S:
                self._flush_save()
                self.running = False
                self.poweroff()

        if self._save_at is not None and now >= self._save_at:
            self._flush_save()

    # Events -------------------------------------------------------------

    def handle(self, event: Event) -> None:
        if self.state is State.SHUTDOWN:
            return
        log.debug("%s in %s", event.value, self.state.value)
        if event in (Event.TURN_CW, Event.TURN_CCW):
            self._turn(1 if event is Event.TURN_CW else -1)
        elif event is Event.PRESS:
            self._press()
        elif event is Event.LONG_ARMED:
            self.audio.play_effect("tick")
        elif event is Event.LONG_PRESS:
            self._go_home()
        elif event is Event.SHUTDOWN:
            self._shutdown()
        elif event in (Event.VOLUME_UP, Event.VOLUME_DOWN):
            step = self.cfg.volume_step if event is Event.VOLUME_UP else -self.cfg.volume_step
            self._set_volume(self.volume + step)
        elif event is Event.QUIT:
            self.running = False

    def _turn(self, direction: int) -> None:
        # The first click away from home re-tunes the last station instead of skipping it.
        if self.state is not State.HOME:
            count = len(self.library.stations)
            target = self.index + direction
            if self.cfg.wrap_dial:
                target %= count
            elif not 0 <= target < count:
                self.audio.play_effect("blip")
                return
            self.index = target
        self.audio.stop_music()
        self.audio.stop_clip()
        self.audio.play_static()
        self._empty_station = False
        self._autoplay_pending = False
        self.state = State.TUNING
        self._settle_at = self.clock() + self.cfg.tune_settle_s

    def _finish_tuning(self) -> None:
        self.audio.stop_static()
        station = self.station
        log.info("tuned to %s", station.label)
        if station.ident:
            self.audio.play_clip(station.ident)
        self.state = State.TUNED
        self._autoplay_pending = self.cfg.autoplay
        self._schedule_save()

    def _press(self) -> None:
        if self.state is State.HOME:
            if self.library.welcome:
                self.audio.play_clip(self.library.welcome)
        elif self.state is State.TUNING:
            self.audio.stop_static(fade_ms=0)
            self.state = State.TUNED
            self._schedule_save()
            self._start_station()
        elif self.state is State.TUNED:
            self._start_station()
        elif self.state is State.PLAYING:
            if self._empty_station:
                self.audio.stop_static()
            else:
                self.audio.pause()
            self.state = State.PAUSED
        elif self.state is State.PAUSED:
            if self._empty_station:
                self.audio.play_static(quiet=True)
            else:
                self.audio.resume()
            self.state = State.PLAYING

    def _start_station(self) -> None:
        self.audio.stop_clip()
        self._autoplay_pending = False
        self.state = State.PLAYING
        if not self.station.tracks:
            log.info("%s has no tracks; playing dead air", self.station.label)
            self._empty_station = True
            self.audio.play_static(quiet=True)
            return
        self._empty_station = False
        self._play_from(self._track_pos.get(self.index, 0))

    def _advance_track(self) -> None:
        self._play_from(self._track_pos.get(self.index, 0) + 1)

    def _play_from(self, position: int) -> None:
        tracks = self.station.tracks
        for attempt in range(len(tracks)):
            pos = (position + attempt) % len(tracks)
            if self.audio.play_track(tracks[pos]):
                self._track_pos[self.index] = pos
                self._track_started = self.clock()
                return
        log.error("no playable tracks in %s", self.station.label)
        self._empty_station = True
        self.audio.play_static(quiet=True)

    def _go_home(self) -> None:
        self.audio.stop_all()
        self.audio.play_effect("home")
        self._empty_station = False
        self._autoplay_pending = False
        self.state = State.HOME
        log.info("home")

    def _shutdown(self) -> None:
        log.info("shutdown requested")
        self.audio.stop_all()
        self.audio.play_effect("goodbye")
        self.state = State.SHUTDOWN
        self._shutdown_at = self.clock()

    def _set_volume(self, volume: float) -> None:
        self.volume = round(min(max(volume, 0.0), 1.0), 3)
        self.audio.set_volume(self.volume)
        self.audio.play_effect("blip")
        self._schedule_save()

    # Persistence --------------------------------------------------------

    def _schedule_save(self) -> None:
        self._save_at = self.clock() + SAVE_DELAY_S

    def _flush_save(self) -> None:
        self._save_at = None
        if self.store:
            self.store.save({"station": self.index, "volume": self.volume})
