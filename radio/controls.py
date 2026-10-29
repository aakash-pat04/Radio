"""Rotary encoder and button input.

The decoding and press-timing logic is pure Python so it can be unit-tested
on any machine. GpioControls wires it to the real pins with gpiozero;
KeyboardControls drives the same events from a terminal for testing.
"""
from __future__ import annotations

import enum
import logging
import os
import queue
import sys
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)


class Event(enum.Enum):
    TURN_CW = "turn_cw"
    TURN_CCW = "turn_ccw"
    PRESS = "press"  # short click
    LONG_ARMED = "long_armed"  # still held at the long-press threshold
    LONG_PRESS = "long_press"  # released after the long-press threshold
    SHUTDOWN = "shutdown"  # held past the shutdown threshold
    VOLUME_UP = "volume_up"  # turned clockwise while held
    VOLUME_DOWN = "volume_down"
    QUIT = "quit"


# Index (previous_state << 2) | new_state, where state = (A << 1) | B.
# Clockwise Gray-code order is 00 -> 01 -> 11 -> 10 -> 00. Transitions where
# both bits change at once are impossible on a real encoder, so they count as
# noise (0), as do "no change" entries. A bounce (forward then back) sums to 0.
_TRANSITIONS = (0, +1, -1, 0, -1, 0, 0, +1, +1, 0, 0, -1, 0, -1, +1, 0)
_REST_BOTH_HIGH = 0b11
_REST_BOTH_LOW = 0b00


class QuadratureDecoder:
    """Turns raw A/B pin levels into whole detent steps, ignoring contact bounce.

    A step is only reported when the encoder reaches a rest (detent) position,
    so bounces and missed edges between detents cannot produce extra steps.
    """

    def __init__(self, transitions_per_detent: int = 4, a: int = 1, b: int = 1):
        if transitions_per_detent not in (2, 4):
            raise ValueError("transitions_per_detent must be 2 or 4")
        self._half = transitions_per_detent // 2
        # Full-step KY-040s rest with both pins pulled high; half-step ones
        # also rest with both low.
        self._rest = (
            {_REST_BOTH_HIGH}
            if transitions_per_detent == 4
            else {_REST_BOTH_HIGH, _REST_BOTH_LOW}
        )
        self._state = (a << 1) | b
        self._accum = 0

    def update(self, a: int, b: int) -> int:
        """Feed the current pin levels; returns +1, -1 or 0 detents."""
        new = (a << 1) | b
        if new == self._state:
            return 0
        self._accum += _TRANSITIONS[(self._state << 2) | new]
        self._state = new
        if new not in self._rest:
            return 0
        step = 0
        if self._accum >= self._half:
            step = 1
        elif self._accum <= -self._half:
            step = -1
        self._accum = 0
        return step


class PressClassifier:
    """Classifies button presses: short, long, shutdown hold, or hold-and-turn volume."""

    def __init__(
        self,
        long_press_s: float,
        shutdown_hold_s: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._long = long_press_s
        self._shutdown = shutdown_hold_s
        self._clock = clock
        self._down_at: float | None = None
        self._armed = False
        self._shutdown_sent = False
        self._volume_mode = False

    @property
    def is_down(self) -> bool:
        return self._down_at is not None

    def press(self) -> list[Event]:
        self._down_at = self._clock()
        self._armed = False
        self._shutdown_sent = False
        self._volume_mode = False
        return []

    def rotate(self, step: int) -> list[Event]:
        if step == 0:
            return []
        if self._down_at is None:
            return [Event.TURN_CW if step > 0 else Event.TURN_CCW]
        self._volume_mode = True
        return [Event.VOLUME_UP if step > 0 else Event.VOLUME_DOWN]

    def poll(self) -> list[Event]:
        """Call regularly while running; reports thresholds crossed while still held."""
        if self._down_at is None or self._volume_mode:
            return []
        held = self._clock() - self._down_at
        events = []
        if not self._armed and held >= self._long:
            self._armed = True
            events.append(Event.LONG_ARMED)
        if not self._shutdown_sent and held >= self._shutdown:
            self._shutdown_sent = True
            events.append(Event.SHUTDOWN)
        return events

    def release(self) -> list[Event]:
        if self._down_at is None:
            return []
        held = self._clock() - self._down_at
        self._down_at = None
        if self._volume_mode or self._shutdown_sent:
            return []
        if held >= self._shutdown:
            return [Event.SHUTDOWN]
        if held >= self._long:
            return [Event.LONG_PRESS]
        return [Event.PRESS]


class GpioControls:
    """KY-040 on the Pi's GPIO pins. Events are put on the shared queue."""

    def __init__(self, cfg, events: "queue.Queue[Event]"):
        from gpiozero import Button, DigitalInputDevice

        self._events = events
        self._lock = threading.Lock()
        self._reverse = cfg.reverse_rotation
        self._classifier = PressClassifier(cfg.long_press_s, cfg.shutdown_hold_s)
        # The KY-040 has its own 10k pull-ups on CLK/DT; enabling the internal
        # ones too is harmless. No bounce_time here: the decoder filters bounce.
        self._a = DigitalInputDevice(cfg.pin_clk, pull_up=True)
        self._b = DigitalInputDevice(cfg.pin_dt, pull_up=True)
        self._decoder = QuadratureDecoder(cfg.transitions_per_detent, *self._levels())
        # Many KY-040 boards leave the SW pull-up unpopulated, so use the Pi's.
        self._button = Button(cfg.pin_sw, pull_up=True, bounce_time=cfg.button_bounce_s)

        for device in (self._a, self._b):
            device.when_activated = self._on_edge
            device.when_deactivated = self._on_edge
        self._button.when_pressed = self._on_press
        self._button.when_released = self._on_release

    def _levels(self) -> tuple[int, int]:
        # With pull_up=True gpiozero reports a low pin as active (1); the
        # decoder wants raw electrical levels.
        return 1 - int(self._a.value), 1 - int(self._b.value)

    def _emit(self, events: list[Event]) -> None:
        for event in events:
            self._events.put(event)

    def _on_edge(self) -> None:
        with self._lock:
            step = self._decoder.update(*self._levels())
            if self._reverse:
                step = -step
            self._emit(self._classifier.rotate(step))

    def _on_press(self) -> None:
        with self._lock:
            self._emit(self._classifier.press())

    def _on_release(self) -> None:
        with self._lock:
            self._emit(self._classifier.release())

    def poll(self) -> None:
        with self._lock:
            self._emit(self._classifier.poll())

    def close(self) -> None:
        for device in (self._a, self._b, self._button):
            device.close()


_KEYS = {
    "\x1b[C": Event.TURN_CW,
    "d": Event.TURN_CW,
    "\x1b[D": Event.TURN_CCW,
    "a": Event.TURN_CCW,
    " ": Event.PRESS,
    "\n": Event.PRESS,
    "l": Event.LONG_PRESS,
    "s": Event.SHUTDOWN,
    "+": Event.VOLUME_UP,
    "=": Event.VOLUME_UP,
    "-": Event.VOLUME_DOWN,
    "q": Event.QUIT,
}

KEYBOARD_HELP = (
    "Keys: <-/-> or a/d tune, space/enter press, l long press (home), "
    "+/- volume, s shutdown hold, q quit"
)


class KeyboardControls:
    """Terminal stand-in for the encoder, for testing on a Mac or over SSH."""

    def __init__(self, events: "queue.Queue[Event]"):
        import termios
        import tty

        self._events = events
        self._fd = sys.stdin.fileno()
        self._saved = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()
        print(KEYBOARD_HELP, flush=True)

    def _read(self) -> None:
        while True:
            key = os.read(self._fd, 1).decode(errors="ignore")
            if not key:
                return
            if key == "\x1b":
                key += os.read(self._fd, 2).decode(errors="ignore")
            event = _KEYS.get(key.lower() if len(key) == 1 else key)
            if event is not None:
                self._events.put(event)

    def poll(self) -> None:
        pass

    def close(self) -> None:
        import termios

        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
