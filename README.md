# Five Years FM

An offline anniversary radio for a Raspberry Pi 2. A rotary encoder tunes between relationship-themed stations. Each station has a voice ident and its own recordings. It boots straight into the radio, and nothing needs the internet.

**Revision 1 is audio only**: an encoder and the 3.5 mm jack to a powered speaker, with no screen. Follow [docs/REV1_GUIDE.md](docs/REV1_GUIDE.md) on the Pi, stage by stage.

| Control | Action |
|---|---|
| Turn | Tune: static, then the station ident |
| Press | Play / pause the station (at home: replay the welcome) |
| Hold 1.5 s | Back to home |
| Hold + turn | Volume |
| Hold 8 s | Safe shutdown |

## Develop on the Mac
```bash
python3 -m venv .venv
.venv/bin/pip install pytest pygame-ce   # pygame-ce has wheels for new Pythons; the Pi uses apt's pygame
.venv/bin/python -m pytest
.venv/bin/python -m radio --check --media media-example
.venv/bin/python -m radio --keyboard --media media-example
```
Regenerate the built-in sounds with `python3 tools/make_sounds.py`. Regenerate the placeholder stations with `tools/make_placeholder_media.sh` (macOS `say`).

## Layout
- `radio/`: the app (pygame mixer, gpiozero; no pip dependencies on the Pi)
- `assets/sounds/`: generated static and chimes
- `media-example/`: six placeholder stations; real media goes in `~/radio-media` on the Pi
- `tools/`: media prep, encoder calibration, USB dongle report
- `deploy/`: install script, systemd units, safe update and automatic rollback
- `tests/`: decoder, press timing, station loading and state machine tests
