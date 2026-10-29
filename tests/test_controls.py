from radio.controls import Event, PressClassifier, QuadratureDecoder


def feed(decoder, levels):
    return [step for step in (decoder.update(a, b) for a, b in levels) if step]


def cw_cycle():
    # Clockwise Gray order 00 -> 01 -> 11 -> 10 -> 00, starting and ending at rest 11.
    return [(1, 0), (0, 0), (0, 1), (1, 1)]


def ccw_cycle():
    return list(reversed([(1, 1)] + cw_cycle()[:-1]))


def test_full_step_one_detent_per_cycle():
    decoder = QuadratureDecoder(4)
    assert feed(decoder, cw_cycle()) == [1]
    assert feed(decoder, cw_cycle() * 3) == [1, 1, 1]
    assert feed(decoder, ccw_cycle()) == [-1]


def test_bounce_between_detents_is_ignored():
    decoder = QuadratureDecoder(4)
    # Contact chatter on the first edge, then a clean cycle.
    chatter = [(1, 0), (1, 1), (1, 0), (1, 1), (1, 0)]
    assert feed(decoder, chatter + cw_cycle()[1:]) == [1]


def test_bounce_at_rest_does_not_step():
    decoder = QuadratureDecoder(4)
    assert feed(decoder, [(1, 0), (1, 1)] * 10) == []


def test_missed_edge_still_counts_direction():
    decoder = QuadratureDecoder(4)
    # 11 -> 10 -> 00 -> (01 missed) -> 11: the impossible 00->11 jump counts 0.
    assert feed(decoder, [(1, 0), (0, 0), (1, 1)]) == [1]


def test_half_step_encoder_rests_at_00_and_11():
    decoder = QuadratureDecoder(2)
    assert feed(decoder, cw_cycle()) == [1, 1]
    assert feed(decoder, ccw_cycle()) == [-1, -1]


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def make(clock):
    return PressClassifier(1.5, 8.0, clock)


def test_short_press():
    clock = Clock()
    pc = make(clock)
    pc.press()
    clock.now += 0.2
    assert pc.poll() == []
    assert pc.release() == [Event.PRESS]


def test_long_press_arms_then_fires_on_release():
    clock = Clock()
    pc = make(clock)
    pc.press()
    clock.now += 1.6
    assert pc.poll() == [Event.LONG_ARMED]
    assert pc.poll() == []
    clock.now += 1.0
    assert pc.release() == [Event.LONG_PRESS]


def test_long_press_without_poll():
    clock = Clock()
    pc = make(clock)
    pc.press()
    clock.now += 2.0
    assert pc.release() == [Event.LONG_PRESS]


def test_shutdown_hold_fires_once_while_held():
    clock = Clock()
    pc = make(clock)
    pc.press()
    clock.now += 1.6
    assert pc.poll() == [Event.LONG_ARMED]
    clock.now += 7.0
    assert pc.poll() == [Event.SHUTDOWN]
    clock.now += 1.0
    assert pc.poll() == []
    assert pc.release() == []


def test_turn_while_held_is_volume_and_cancels_press():
    clock = Clock()
    pc = make(clock)
    assert pc.rotate(1) == [Event.TURN_CW]
    pc.press()
    assert pc.rotate(1) == [Event.VOLUME_UP]
    assert pc.rotate(-1) == [Event.VOLUME_DOWN]
    clock.now += 9.0
    assert pc.poll() == []
    assert pc.release() == []
    assert pc.rotate(-1) == [Event.TURN_CCW]


def test_release_without_press_is_ignored():
    assert make(Clock()).release() == []
