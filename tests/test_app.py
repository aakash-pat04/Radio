import queue
from pathlib import Path

import pytest

from radio.app import App, State, StateStore
from radio.config import Config
from radio.controls import Event
from radio.stations import Library, Station


class FakeAudio:
    def __init__(self):
        self.calls = []
        self.volume = None
        self.music = False
        self.clip = False
        self.effect = False
        self.static = False
        self.bad_tracks = set()

    def set_volume(self, v):
        self.volume = v

    def play_static(self, quiet=False):
        self.static = True
        self.calls.append(("static", quiet))

    def stop_static(self, fade_ms=250):
        self.static = False

    def play_clip(self, path):
        self.clip = True
        self.calls.append(("clip", path.name))
        return True

    def clip_busy(self):
        return self.clip

    def stop_clip(self):
        self.clip = False

    def play_effect(self, name):
        self.effect = True
        self.calls.append(("effect", name))

    def effect_busy(self):
        return self.effect

    def play_track(self, path):
        if path.name in self.bad_tracks:
            return False
        self.music = True
        self.calls.append(("track", path.name))
        return True

    def music_busy(self):
        return self.music

    def pause(self):
        self.calls.append(("pause",))

    def resume(self):
        self.calls.append(("resume",))

    def stop_music(self):
        self.music = False

    def stop_all(self):
        self.music = self.clip = self.static = self.effect = False

    def last(self, kind):
        return next((c for c in reversed(self.calls) if c[0] == kind), None)


class FakeControls:
    def poll(self):
        pass


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def station(name, tracks):
    folder = Path("/media") / name
    return Station("88.1", name, folder, folder / "ident.ogg", [folder / t for t in tracks])


@pytest.fixture
def rig(tmp_path):
    cfg = Config(media_dir=tmp_path)
    library = Library(
        tmp_path,
        [station("a", ["a1.ogg", "a2.ogg"]), station("b", ["b1.ogg"]), station("c", [])],
        Path("/media/home/welcome.ogg"),
    )
    audio, clock, events = FakeAudio(), Clock(), queue.Queue()
    powered_off = []
    store = StateStore(tmp_path / "state.json")
    app = App(cfg, library, audio, FakeControls(), events, store, lambda: powered_off.append(1), clock)
    app.start()

    def send(*evts, advance=0.0):
        for e in evts:
            events.put(e)
        app.step()
        if advance:
            clock.now += advance
            app.step()

    return app, audio, clock, send, powered_off, store


def test_boot_plays_welcome_and_sits_at_home(rig):
    app, audio, *_ = rig
    assert app.state is State.HOME
    assert audio.last("clip") == ("clip", "welcome.ogg")
    assert audio.volume == 0.7


def test_first_turn_from_home_tunes_current_station(rig):
    app, audio, clock, send, *_ = rig
    send(Event.TURN_CW)
    assert app.state is State.TUNING and app.index == 0 and audio.static
    send(advance=0.7)
    assert app.state is State.TUNED
    assert not audio.static
    assert audio.last("clip") == ("clip", "ident.ogg")


def test_turning_moves_and_wraps(rig):
    app, audio, clock, send, *_ = rig
    send(Event.TURN_CW, Event.TURN_CW, Event.TURN_CW, Event.TURN_CW)
    assert app.index == 0  # 0 (from home) -> 1 -> 2 -> 0
    send(Event.TURN_CCW)
    assert app.index == 2


def test_no_wrap_stops_at_end(rig):
    app, audio, clock, send, *_ = rig
    app.cfg.wrap_dial = False
    send(Event.TURN_CW, Event.TURN_CCW)
    assert app.index == 0
    assert audio.last("effect") == ("effect", "blip")


def test_press_plays_then_pauses_then_resumes(rig):
    app, audio, clock, send, *_ = rig
    send(Event.TURN_CW, advance=0.7)
    send(Event.PRESS)
    assert app.state is State.PLAYING and audio.last("track") == ("track", "a1.ogg")
    send(Event.PRESS)
    assert app.state is State.PAUSED and audio.last("pause")
    send(Event.PRESS)
    assert app.state is State.PLAYING and audio.last("resume")


def test_press_while_tuning_skips_ident(rig):
    app, audio, clock, send, *_ = rig
    send(Event.TURN_CW, Event.PRESS)
    assert app.state is State.PLAYING
    assert audio.last("track") == ("track", "a1.ogg")


def test_playlist_advances_and_loops(rig):
    app, audio, clock, send, *_ = rig
    send(Event.TURN_CW, Event.PRESS)
    audio.music = False  # track ended
    send(advance=1.0)
    assert audio.last("track") == ("track", "a2.ogg")
    audio.music = False
    send(advance=1.0)
    assert audio.last("track") == ("track", "a1.ogg")


def test_unplayable_track_is_skipped(rig):
    app, audio, clock, send, *_ = rig
    audio.bad_tracks = {"a1.ogg"}
    send(Event.TURN_CW, Event.PRESS)
    assert audio.last("track") == ("track", "a2.ogg")


def test_empty_station_plays_quiet_static(rig):
    app, audio, clock, send, *_ = rig
    send(Event.TURN_CCW)  # from home: tune station 0
    send(Event.TURN_CCW)  # wrap to station 2 (empty)
    send(Event.PRESS)
    assert app.state is State.PLAYING and audio.last("static") == ("static", True)
    send(Event.PRESS)
    assert app.state is State.PAUSED and not audio.static


def test_long_press_goes_home(rig):
    app, audio, clock, send, *_ = rig
    send(Event.TURN_CW, Event.PRESS, Event.LONG_ARMED)
    assert audio.last("effect") == ("effect", "tick")
    send(Event.LONG_PRESS)
    assert app.state is State.HOME and not audio.music
    assert audio.last("effect") == ("effect", "home")


def test_volume_clamps_and_persists(rig):
    app, audio, clock, send, _, store = rig
    for _ in range(10):
        send(Event.VOLUME_UP)
    assert audio.volume == 1.0
    send(advance=3.0)
    assert store.load()["volume"] == 1.0


def test_station_and_volume_restored(tmp_path, rig):
    app, audio, clock, send, _, store = rig
    send(Event.TURN_CW, Event.TURN_CW, advance=0.7)
    send(Event.VOLUME_DOWN, advance=3.0)
    again = App(app.cfg, app.library, FakeAudio(), FakeControls(), queue.Queue(), store)
    assert again.index == 1
    assert again.volume == pytest.approx(0.65)


def test_corrupt_state_file_uses_defaults(tmp_path, rig):
    app, *_ = rig
    path = tmp_path / "bad.json"
    path.write_text('{"station": 99, "volume": "loud"}')
    again = App(app.cfg, app.library, FakeAudio(), FakeControls(), queue.Queue(), StateStore(path))
    assert again.index == 2  # clamped to the last station
    assert again.volume == 0.7


def test_shutdown_waits_for_chime_then_powers_off(rig):
    app, audio, clock, send, powered_off, _ = rig
    send(Event.TURN_CW, Event.PRESS, Event.SHUTDOWN)
    assert app.state is State.SHUTDOWN and audio.last("effect") == ("effect", "goodbye")
    assert powered_off == []
    send(Event.TURN_CW)  # ignored once shutting down
    assert app.state is State.SHUTDOWN
    audio.effect = False
    send()
    assert powered_off == [1] and not app.running


def test_quit_stops_loop(rig):
    app, audio, clock, send, *_ = rig
    send(Event.QUIT)
    assert not app.running
