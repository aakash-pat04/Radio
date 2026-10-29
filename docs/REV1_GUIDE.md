# Five Years FM — Revision 1 build guide (audio + encoder, no screen)

Work through the stages in order. Each stage says what success looks like.
**STOP** means: send the output to Claude before going on, because the next
step depends on it.

Rev 1 has no screen. The PiTFT failed SPI bring-up (white screen,
`unknown chip id 0x0000`, STMPE610 probe failure), so it stays in the drawer
until Rev 2. Every station's audio, voice ident and the anniversary letter
work without it.

Commands marked **(Pi)** run in the Pi's shell, through the Raspberry Pi
Connect remote shell or SSH. Commands marked **(Mac)** run in Terminal on
the Mac.

---

## A. Hardware-validation checklist

### A1. The Pi itself (Pi)
```bash
cat /proc/device-tree/model; echo
uname -m
cat /etc/os-release | head -4
vcgencmd get_throttled
```
**Success looks like:**
- `Raspberry Pi 2 Model B Rev 1.1` (or `Rev 1.2`)
- `armv7l`
- `PRETTY_NAME="Raspbian GNU/Linux 12 (bookworm)"` or a later release
- `throttled=0x0`

Any other `throttled` value means the Pi has seen undervoltage or overheating. Fix the power (section D3) before going further.

**STOP: send the `os-release` lines.** That's the OS decision in D1.

### A2. Clean up after the PiTFT (Pi)
The PiTFT is unplugged, but its driver settings may still be in the boot config. That's why boot still reports the STMPE610 probe failure. Find them first and don't change anything yet:
```bash
grep -nE "pitft|stmpe|ili9341|fbtft|spi|rotate|fbcon" /boot/firmware/config.txt /boot/firmware/cmdline.txt
ls /etc/modules-load.d/ ; grep -nE "fbtft|stmpe|ili9341" /etc/modules /etc/modules-load.d/* 2>/dev/null
```
**Success looks like:** a few matching lines, or none.

**STOP: paste the full output.** Claude will tell you exactly which lines to comment out. Don't delete lines from `cmdline.txt` by guesswork: it's a single line, and a broken edit stops the Pi booting.

### A3. Speaker and audio jack (Pi)
Wiring:
1. Speaker AUX plug → the Pi's 3.5 mm jack.
2. Speaker USB plug → its own USB charger, not the Pi (see D3).
3. Speaker knob → about one third.

```bash
grep -n "dtparam=audio" /boot/firmware/config.txt
aplay -l
```
**Success looks like:**
- `dtparam=audio=on` (not commented out).
- A card line containing **`bcm2835 Headphones`**, for example `card 0: Headphones [bcm2835 Headphones], device 0: ...`. The card number varies; an HDMI card such as `vc4hdmi` may also appear.

**STOP: paste the `aplay -l` output.** The ALSA default card in D2 depends on it.

After D2 is done, test sound:
```bash
speaker-test -c 2 -t wav -l 1
```
**Success looks like:** a voice says "Front Left" from one side and "Front Right" from the other, and the command exits. If you hear nothing, see J2.

### A4. Rotary encoder (Pi; wire it as in section C first)
Do D2 first so the packages exist. Then:
```bash
cd ~/Radio
python3 tools/encoder_test.py
```
**Success looks like:**
1. Before you touch it, the test prints `idle levels A=1 B=1` and `button is released`.
2. Turn **one click** clockwise, pause, and repeat a few times. Read the `settled` lines:
   - `settled at 11 after 4 transitions` on every click → **full-step** encoder (the default, 4).
   - Alternating `settled at 00 ...`/`settled at 11 ... after 2 transitions` → **half-step** encoder (setting 2).
3. With the right setting there is exactly one `DETENT CW` per clockwise click and one `DETENT CCW` per anticlockwise click.
4. Press briefly and it prints `BUTTON press`. Hold 2 s and release, and it prints `BUTTON long_armed`, then `BUTTON long_press`. Hold 9 s and it prints `BUTTON shutdown`.

**STOP: report the transitions per click, and whether clockwise prints CW.**

If the encoder is half-step or runs backwards, the fix is a line in `/etc/default/radio` (see I3). No code change is needed.

### A5. USB dongles and Bluetooth (Pi)
The Pi 2 has no built-in Wi‑Fi or Bluetooth. Test each dongle **on its own**: unplug the others (keep Ethernet, or whichever dongle you need for the network), plug in one, wait 5 s, then run:
```bash
cd ~/Radio
tools/usb_dongle_report.sh
```
How to read the output:
| You see | Meaning |
|---|---|
| A new `wlan1` (or `wlan0`) and an interface with `driver=rtl8xxxu`/`8192cu`/similar | Wi‑Fi adapter |
| `class=03` `<-- HID` | A keyboard/mouse receiver, for example a Logitech Unifying receiver. Not Bluetooth. |
| `class=e0 sub=01 proto=01 <-- Bluetooth HCI interface`, plus `hci0` under "Bluetooth controllers" | Bluetooth adapter. Install `bluez` and rerun to see `Controller XX:XX:... [default]` in `bluetoothctl`. |

**STOP: send the report for each of the three dongles.** Bluetooth isn't part of Rev 1 either way. The result only decides whether a BT receiver mode is possible later.

---

## B. Decision trees

### B1. LCD HAT (deferred to Rev 2)
```
PiTFT 2.8" (ILI9341 + STMPE610), white screen + chip id 0x0000
└─ Rev 1: removed. Comment out its boot-config lines (A2). Nothing else.
└─ Rev 2 starts here:
   1. Inspect the Pi's header and the PiTFT's 26-pin socket for bent/pushed-in
      pins and solder bridges (magnifier), especially pins 19, 21, 23, 24, 26 (SPI0).
   2. Test the Pi's SPI0 on its own with a loopback test before blaming the PiTFT.
   3. Pi SPI OK + PiTFT still 0x0000 → the PiTFT is probably damaged; replace it.
   4. Pi SPI broken → use a different Pi or a non-SPI display.
```
The encoder pins (GPIO 5/6/13) aren't SPI pins, so a damaged SPI block doesn't affect Rev 1. A4 confirms those pins work.

### B2. Bluetooth
```
A5 report shows class e0/01/01 + hci0 ?
├─ No (for all three)  → No Bluetooth. Rev 1 is the complete gift. Done.
└─ Yes                 → Note which dongle. Rev 2 may add an optional "BT" mode
                         (BlueZ A2DP sink → ALSA). Keep it unplugged until then.
```

---

## C. Wiring (KY-040 → Pi 2)

These pins were chosen because:
- The PiTFT is removed, so the whole header is reachable.
- They are on the outer half of the header (pins 29–39). They stay reachable even if a 26-pin screen goes back on in Rev 2.
- They avoid every pin the PiTFT uses (SPI0, GPIO 18/24/25) and also avoid I²C and UART.

| KY-040 pin | Wire to Pi physical pin | Pi signal |
|---|---|---|
| CLK | **29** | GPIO 5 |
| DT  | **31** | GPIO 6 |
| SW  | **33** | GPIO 13 |
| +   | **17** | **3.3 V**. Never 5 V: the module's pull-ups would put 5 V on the GPIO pins. |
| GND | **39** | Ground |

```
  Pi 2 header (pin 1 is nearest the SD-card end, inner row = odd numbers)
   1 3.3V   o o  2 5V
        ...
  17 3.3V   o o 18        <- KY-040 "+"
        ...
  29 GPIO5  o o 30        <- CLK
  31 GPIO6  o o 32        <- DT
  33 GPIO13 o o 34        <- SW
  35        o o 36
  37        o o 38
  39 GND    o o 40        <- GND
```
Rev 2 note: 3.3 V exists only on pins 1 and 17, both inside the first 26 pins. If a 26-pin screen ever goes back on, feed the `+` wire through a 40-pin stacking header (passive, no extra chips).

First, with the Pi running and nothing connected, confirm the pins are free:
```bash
pinctrl get 5,6,13
```
**Success looks like:** each line shows the pin as an input, e.g. `5: ip ... // GPIO5 = input`, and not an alt function (`a0`…`a5`) or output (`op`). If any pin shows something else, **STOP** and paste it.

Then `sudo poweroff`, unplug the Pi, and wire the encoder with the power off. Pin 1 has a square solder pad on the underside of the board.

Use female-to-female Dupont jumpers, or a 5-wire harness soldered to a 2×20 female header for a neater build inside the box. Leave some slack so the knob can be mounted on the enclosure lid.

---

## D. OS, packages and power

### D1. OS
- If A1 shows **Bookworm or later, 32-bit Lite**: keep it. Rev 1 has no display driver to constrain the OS, and your Raspberry Pi Connect setup already works.
- If it shows **Desktop**: it will work, but the desktop's audio server can grab the sound card. **STOP** and say so, because Lite is simpler.
- If it shows **Bullseye or older**: **STOP**. The paths in this guide (`/boot/firmware`, `pinctrl`) assume Bookworm or later.

### D2. Get the code and install (Pi)
Your Pi already has a read-only clone. Fetch the first real commit:
```bash
cd ~/Radio            # adjust if your clone lives elsewhere
git pull origin main
deploy/install.sh
```
**Success looks like:** the apt install finishes, `visudo` reports `parsed OK`, and the script ends with `== Done. Next: ...`. Then **log out and back in** (or reboot) so the new `audio`/`gpio` groups apply.

Set the default sound card. Use the card **name** from A3, normally `Headphones`:
```bash
printf 'defaults.pcm.card Headphones\ndefaults.ctl.card Headphones\n' | sudo tee /etc/asound.conf
amixer sset PCM 85%
sudo alsactl store
amixer sget PCM
```
**Success looks like:** `amixer sget PCM` shows `Playback ... [85%]`. Now run the `speaker-test` from A3.

Self-check with the bundled example stations:
```bash
python3 -m radio --check
```
**Success looks like:** six stations, each with `ident` and `1 track(s)`, then `audio: mixer opened OK` and `CHECK PASSED`.

### D3. Power (read before the box is closed)
- **Pi:** use a dedicated 5.1 V supply rated **at least 2.5 A**, such as the official Pi PSU.
- **Speaker:** power its USB plug from **its own** USB charger.
- **Don't power the speaker from the Pi's USB ports.** The Pi's USB ports share a limited current budget. An amplifier draws sharp current peaks on loud or bassy passages, which can pull the Pi below its undervoltage threshold and cause crackles, resets or SD-card corruption.
- **One supply for both** is acceptable only if it is a good-quality dual-port charger rated 3.5 A or more in total, with the Pi on a port that can supply 2.5 A.
- **Check under load:** play the radio loudly for a few minutes, then run:
  ```bash
  vcgencmd get_throttled
  dmesg | grep -i voltage
  ```
  **Success looks like:** `throttled=0x0` and no `Undervoltage detected` lines.
- **Hum or whine** that changes with Pi activity is a ground loop. Try separate supplies, or a 3.5 mm ground-loop isolator on the AUX cable.

---

## E. Folder structure and assets

```
~/Radio/                       code (read-only git clone; never edit on the Pi)
  radio/                       the app
  assets/sounds/               built-in static, tick, chimes (generated)
  media-example/               placeholder stations (computer voice + tones)
  tools/  deploy/  docs/  tests/
~/radio-media/                 YOUR media (not in git)
  stations.json
  home/welcome.ogg             played at boot and when you press at home
  88.1-first-signal/
    ident.ogg                  "You're listening to 88.1, First Signal"
    01-song.ogg  02-story.ogg  played in filename order, looping
    memory.txt  photos/        kept for the screen revision (ignored in Rev 1)
  ...
  100.0-future-frequency/
    ident.ogg
    01-letter.ogg              you reading the anniversary letter
    02-future-plans.ogg
    letter.txt                 for Rev 2
```
`stations.json` lists the stations in dial order (copy `media-example/stations.json` to start). Each `folder` must match a directory name.

Recording tips:
- Record idents and letters on your phone in a quiet room, about 20 cm from the mic.
- Name them `ident.m4a`, `welcome.m4a`, `01-letter.m4a` and so on. Any of m4a, mp3, wav, aiff or flac is fine.
- Leave half a second of silence at the start and end.

Build the media on the Mac:
```bash
brew install ffmpeg
cp -R ~/Desktop/Projects/Radio/media-example ~/Desktop/radio-source   # start from the example, then replace files
tools/prepare_media.sh ~/Desktop/radio-source ~/Desktop/radio-media
```
**Success looks like:** an `audio ... -> ....ogg` line for every recording, then `Done: N audio file(s) converted`.

Delete the placeholder `01-placeholder-tone.wav` and `ident.wav` files from the source before converting. Otherwise they stay in the playlist.

Copy the media to the Pi. Use one of these two options:
- **Over SSH (Mac)**, if SSH is enabled on the Pi:
  ```bash
  rsync -av --delete ~/Desktop/radio-media/ USER@PI-HOSTNAME.local:radio-media/
  ```
- **With a USB stick:** copy the `radio-media` folder onto the stick on the Mac, then on the Pi:
  ```bash
  lsblk -o NAME,SIZE,FSTYPE,LABEL      # find the stick, e.g. sda1
  sudo mount /dev/sda1 /mnt
  rsync -av --delete /mnt/radio-media/ ~/radio-media/
  sudo umount /mnt
  ```

Then check and pick it up (Pi):
```bash
sudo systemctl stop radio; python3 -m radio --check; sudo systemctl start radio
```
**Success looks like:** `media: /home/USER/radio-media`, your six stations with track counts, no `FAIL`, and `CHECK PASSED`. `WARN` lines point at missing idents or tracks; the radio still runs.

---

## F. The application code

| File | Role |
|---|---|
| `radio/__main__.py` | Entry point: `python3 -m radio [--keyboard] [--check] [--media PATH] [-v]`. Falls back to the example media if yours is broken. |
| `radio/config.py` | Pins, timings and volume, all overridable from `/etc/default/radio` |
| `radio/stations.py` | Reads `stations.json` and the station folders, and warns about missing pieces |
| `radio/app.py` | State machine (HOME → TUNING → TUNED → PLAYING ⇄ PAUSED, plus SHUTDOWN). Remembers the last station and volume. |
| `radio/audio.py` | pygame mixer with no display: a looping static channel, a voice channel for idents, an effects channel and the music stream |
| `radio/selfcheck.py` | `--check`, used by the update script before every restart |

How it behaves:
| You do | The radio does |
|---|---|
| Turn the knob | Static while turning. About 0.6 s after you stop, the static fades and that station's ident plays. |
| Press | Starts the station's recordings, which loop. Press again to pause or resume. At home, it replays the welcome. |
| Hold 1.5 s and release | A tick sounds at 1.5 s. On release, a chime plays and the radio returns to home and stops playback. |
| Hold and turn | Volume up or down, with a blip at the new level. |
| Hold 8 s | Goodbye chime, then the Pi shuts down safely. Wait for the green LED to stop flashing before unplugging. |

## G. Encoder code (in `radio/controls.py`)
- **`QuadratureDecoder`** debounces in software:
  - A transition table rejects impossible jumps.
  - Bounces between two states cancel out.
  - A step is only counted when the encoder settles in a detent, so chatter can't add or skip stations.
- **`PressClassifier`** times the button:
  - short press;
  - long press (fires on release, with a tick at the threshold);
  - shutdown hold (fires while still held);
  - "turn while held", which switches to volume and cancels the press.
  - The button also has a 30 ms hardware-level debounce (`bounce_time`).
- **`GpioControls`** connects both to gpiozero callbacks.
- **`KeyboardControls`** maps the same events to keys for testing without hardware.

## H. Audio playback and Bluetooth
- Audio goes through ALSA to the 3.5 mm jack (D2), at 44.1 kHz with a 2048-frame buffer. Raise `RADIO_BUFFER_FRAMES=4096` in `/etc/default/radio` if playback crackles.
- Volume works in three layers:
  1. ALSA `PCM` is fixed at 85% (D2).
  2. The speaker knob is set once to a comfortable maximum.
  3. Everyday volume is hold-and-turn, saved across reboots.
- Use OGG (from `prepare_media.sh`) for the lowest CPU load on the Pi 2. MP3 and WAV also play.
- **Bluetooth:** not in Rev 1 (see B2).

---

## I. Auto-start (systemd)

### I1. Enable (Pi)
`deploy/install.sh` already installed the units. Start the radio and make it start on every boot:
```bash
sudo systemctl enable --now radio
systemctl status radio --no-pager
```
**Success looks like:** `Active: active (running)`, and you hear the welcome clip. Now reboot:
```bash
sudo reboot
```
**Success looks like:** within about 30–60 s of power-on, the welcome plays with no keyboard or login.

### I2. What the service does
- `Restart=on-failure`: a crash restarts the app after 3 s.
- Five crashes within two minutes → `radio-rollback.service` checks the code back out at the `known-good` tag and starts it again. The rollback script lives in `/usr/local/bin`, so a broken checkout can't break its own recovery.
- `ConditionPathExists=!/boot/firmware/radio-disabled` is a kill switch (J3).
- Overrides live in `/etc/default/radio`, which updates never touch.

### I3. Settings (Pi)
```bash
sudo nano /etc/default/radio      # uncomment e.g. RADIO_TRANSITIONS_PER_DETENT=2 or RADIO_REVERSE=1
sudo systemctl restart radio
```

---

## J. Test plan, maintenance and troubleshooting

### J1. End-to-end test (in this order)
1. `python3 -m radio --check` → `CHECK PASSED`.
2. Run interactively without the service, using the keyboard:
   ```bash
   sudo systemctl stop radio
   python3 -m radio --keyboard -v
   ```
   Then, with the keys printed at startup: → (static, then ident), space (plays), space (pauses), `l` (home chime), `+`/`-` (blips), `q` (quit).
3. Same again with the real knob: `python3 -m radio -v`, then Ctrl+C.
4. `sudo systemctl start radio`. Turn through all six stations and play each one.
5. Hold 8 s → goodbye chime → the Pi powers off. Power back on → the welcome plays, and the last station and volume are remembered.
6. Run the loud-playback power check (D3).
7. Pull the plug while playing, then power on. It should still boot into the radio. Don't make a habit of this: use the 8 s hold.

### J2. Troubleshooting
| Symptom | Check |
|---|---|
| No sound at all | `aplay -l` shows `Headphones`; `/etc/asound.conf` names it; `amixer sget PCM` isn't 0% or `[off]`; the speaker is powered and its knob is up; then `speaker-test -c 2 -t wav -l 1`. |
| `--check` says `FAIL audio` | Another program is holding the sound card. Run `sudo systemctl stop radio` first. Then check `journalctl -u radio -b --no-pager \| tail -30`. |
| Hiss | Normal for the Pi 2's analogue jack at high speaker gain. Keep the Pi's PCM at 85% and turn the speaker knob down. |
| Hum or whine | Ground loop or noisy supply (D3). |
| Crackles or dropouts | `RADIO_BUFFER_FRAMES=4096`; also run `vcgencmd get_throttled`. |
| Knob turns the wrong way | `RADIO_REVERSE=1` |
| Two stations per click, or one per two clicks | `RADIO_TRANSITIONS_PER_DETENT=2` or `4` (A4). |
| Nothing happens on turn or press | Run `tools/encoder_test.py`; re-check the C wiring and the `pinctrl` output. |
| Button always reads pressed | SW and GND are swapped, or SW is on the wrong pin. |
| Shutdown hold does nothing | `sudo -l` should list `/usr/bin/systemctl poweroff`; rerun `deploy/install.sh`. |
| Radio silent after an update | `journalctl -u radio -u radio-rollback -b --no-pager \| tail -50` |

### J3. Maintenance and recovery
- **Stop the radio** to work on the Pi: `sudo systemctl stop radio`. It comes back on the next boot.
- **Turn auto-start off:** `sudo systemctl disable --now radio`. Turn it back on with `enable --now`.
- **Logs:** `journalctl -u radio -f`
- **Kill switch, without a working shell:**
  1. Put the SD card in the Mac.
  2. Run `touch /Volumes/bootfs/radio-disabled`.
  3. Eject the card and boot the Pi. The radio won't start.
  4. Re-enable later with `sudo rm /boot/firmware/radio-disabled && sudo systemctl start radio`.
- **Updating the code:** never `git pull` or edit files on the Pi after install. Use:
  ```bash
  ~/Radio/deploy/update.sh            # or: deploy/update.sh <tag-or-commit>
  ```
  It fetches, checks out the new commit, runs `--check`, restarts, and waits 15 s to confirm the service stays up. It ends with `== OK: radio running abc1234, tagged known-good`. On any failure it prints `!! ... rolling back` and returns to the previous commit.
- **Manual rollback:**
  ```bash
  cd ~/Radio && git checkout --detach known-good && sudo systemctl restart radio
  ```
- **Before giving the gift:** make a full SD-card image backup from the Mac. It's the ultimate recovery path.
