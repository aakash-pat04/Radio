"""Entry point: python3 -m radio [--keyboard] [--check] [--media PATH] [-v]"""
from __future__ import annotations

import argparse
import logging
import queue
import signal
import subprocess
import sys
from pathlib import Path

from .config import EXAMPLE_MEDIA, Config
from .controls import Event
from .stations import MediaError, load_library

log = logging.getLogger("radio")


def _is_raspberry_pi() -> bool:
    try:
        return "Raspberry Pi" in Path("/proc/device-tree/model").read_text(errors="ignore")
    except OSError:
        return False


def poweroff() -> None:
    if not _is_raspberry_pi():
        log.info("shutdown gesture received (not a Pi, so not powering off)")
        return
    log.info("powering off")
    subprocess.run(["sudo", "-n", "systemctl", "poweroff"], check=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radio", description="Five Years FM")
    parser.add_argument("--keyboard", action="store_true", help="use the keyboard instead of GPIO")
    parser.add_argument("--check", action="store_true", help="validate media and audio, then exit")
    parser.add_argument("--media", help="media folder (default: ~/radio-media or media-example)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    cfg = Config.from_env(args.media)

    if args.check:
        from .selfcheck import run_check

        return run_check(cfg)

    try:
        library = load_library(cfg.media_dir)
    except MediaError as exc:
        # Broken personal media should not leave the gift silent.
        log.error("media problem: %s; falling back to %s", exc, EXAMPLE_MEDIA)
        cfg.media_dir = EXAMPLE_MEDIA
        library = load_library(EXAMPLE_MEDIA)
    for warning in library.warnings:
        log.warning(warning)

    from .app import App, StateStore
    from .audio import AudioEngine

    events: "queue.Queue[Event]" = queue.Queue()
    audio = AudioEngine(cfg)
    if args.keyboard:
        from .controls import KeyboardControls

        controls = KeyboardControls(events)
    else:
        try:
            from .controls import GpioControls

            controls = GpioControls(cfg, events)
        except Exception as exc:
            audio.close()
            log.error("GPIO unavailable (%s). On a non-Pi machine use --keyboard.", exc)
            return 1

    signal.signal(signal.SIGTERM, lambda *_: events.put(Event.QUIT))
    app = App(cfg, library, audio, controls, events, StateStore(cfg.state_file), poweroff)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        controls.close()
        audio.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
