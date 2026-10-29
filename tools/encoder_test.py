#!/usr/bin/env python3
"""Encoder calibration and wiring test. Run on the Pi with the radio service stopped:

    sudo systemctl stop radio      # if it is installed
    python3 tools/encoder_test.py

Turn the knob ONE click at a time, pausing between clicks, and read the "settled" lines:
  * "settled at 11 after 4 transitions" on every click     -> full-step encoder (setting 4)
  * alternating "settled at 00 / at 11 after 2 transitions" -> half-step encoder (setting 2)
Then check the "DETENT" lines: exactly one per click, CW when turned clockwise.
Press, long-press (>1.5 s) and hold (>8 s) the knob to see button events.
Ctrl+C to exit.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gpiozero import Button, DigitalInputDevice  # noqa: E402

from radio.config import Config  # noqa: E402
from radio.controls import PressClassifier, QuadratureDecoder  # noqa: E402

cfg = Config.from_env()
a = DigitalInputDevice(cfg.pin_clk, pull_up=True)
b = DigitalInputDevice(cfg.pin_dt, pull_up=True)
button = Button(cfg.pin_sw, pull_up=True, bounce_time=cfg.button_bounce_s)


def levels() -> tuple[int, int]:
    return 1 - int(a.value), 1 - int(b.value)


decoder = QuadratureDecoder(cfg.transitions_per_detent, *levels())
classifier = PressClassifier(cfg.long_press_s, cfg.shutdown_hold_s)
last = (levels()[0] << 1) | levels()[1]
lock = threading.Lock()
since_settle = 0
last_edge = 0.0
total = 0

print(f"GPIO CLK={cfg.pin_clk} DT={cfg.pin_dt} SW={cfg.pin_sw}; "
      f"transitions_per_detent={cfg.transitions_per_detent}; reverse={cfg.reverse_rotation}")
print(f"idle levels A={levels()[0]} B={levels()[1]} (a KY-040 at rest normally reads A=1 B=1)")
print(f"button is {'PRESSED (check SW wiring!)' if button.is_pressed else 'released'}")


def on_edge() -> None:
    global last, since_settle, last_edge, total
    la, lb = levels()
    state = (la << 1) | lb
    with lock:
        if state == last:
            return
        last = state
        since_settle += 1
        last_edge = time.monotonic()
    step = decoder.update(la, lb)
    if cfg.reverse_rotation:
        step = -step
    if step:
        total += step
        print(f"DETENT {'CW ' if step > 0 else 'CCW'}  position={total}")


for device in (a, b):
    device.when_activated = on_edge
    device.when_deactivated = on_edge


def show(events) -> None:
    for event in events:
        print(f"BUTTON {event.value}")


button.when_pressed = lambda: (print("BUTTON down"), show(classifier.press()))
button.when_released = lambda: (print("BUTTON up"), show(classifier.release()))

def report_settled() -> None:
    """Once the knob has been still for 0.3 s, say where it came to rest."""
    global since_settle
    with lock:
        if since_settle and time.monotonic() - last_edge > 0.3:
            print(f"  settled at {last >> 1}{last & 1} after {since_settle} transitions")
            since_settle = 0


try:
    while True:
        show(classifier.poll())
        report_settled()
        time.sleep(0.05)
except KeyboardInterrupt:
    print()
finally:
    for device in (a, b, button):
        device.close()
    os._exit(0)
