import threading

import bot


class _FakeStop:
    def __init__(self, clock, cancel=False):
        self.clock = clock
        self.cancel = cancel
        self.set_value = False
        self.waits = []

    def is_set(self):
        return self.set_value

    def set(self):
        self.set_value = True

    def wait(self, timeout):
        self.waits.append(float(timeout))
        self.clock[0] += float(timeout)
        if self.cancel:
            self.set_value = True
            return True
        return False


def test_loop_rest_due_requires_enabled_exact_interval():
    settings = {
        "loop_rest_enabled": True,
        "loop_rest_every": 4,
        "loop_rest_minutes": 5,
    }
    assert bot.loop_rest_due(settings, 3) is False
    assert bot.loop_rest_due(settings, 4) is True
    assert bot.loop_rest_due(settings, 8) is True
    assert bot.loop_rest_due({**settings, "loop_rest_enabled": False}, 4) is False
    assert bot.loop_rest_due({**settings, "loop_rest_minutes": 0}, 4) is False


def test_scheduled_rest_countdown_is_stop_aware(monkeypatch):
    clock = [100.0]
    stop = _FakeStop(clock)
    events = []
    monkeypatch.setattr(bot, "STOP_FLAG", stop)
    monkeypatch.setattr(bot.time, "monotonic", lambda: clock[0])
    monkeypatch.setitem(bot.SETTINGS, "loop_rest_enabled", True)
    monkeypatch.setitem(bot.SETTINGS, "loop_rest_every", 2)
    monkeypatch.setitem(bot.SETTINGS, "loop_rest_minutes", 0.05)

    assert bot.wait_for_scheduled_lobby_rest(2, on_rest_progress=lambda **event: events.append(event)) is True
    assert stop.waits
    assert max(stop.waits) <= 1.0
    assert events[0]["active"] is True
    assert events[-1]["active"] is False
    assert events[-1]["remaining_seconds"] == 0


def test_scheduled_rest_stops_immediately(monkeypatch):
    clock = [200.0]
    stop = _FakeStop(clock, cancel=True)
    monkeypatch.setattr(bot, "STOP_FLAG", stop)
    monkeypatch.setattr(bot.time, "monotonic", lambda: clock[0])
    monkeypatch.setitem(bot.SETTINGS, "loop_rest_enabled", True)
    monkeypatch.setitem(bot.SETTINGS, "loop_rest_every", 1)
    monkeypatch.setitem(bot.SETTINGS, "loop_rest_minutes", 10)

    assert bot.wait_for_scheduled_lobby_rest(1) is False
    assert stop.waits == [1.0]


def test_lobby_tasks_run_before_rest_and_play(monkeypatch):
    frames = iter(("lobby-before", "lobby-after", "boost"))
    order = []
    monkeypatch.setattr(bot, "STOP_FLAG", threading.Event())
    monkeypatch.setattr(bot, "adb_screencap", lambda: next(frames))
    monkeypatch.setattr(bot, "_play_is_dim", lambda _screen, _pos: False)
    monkeypatch.setattr(bot, "_find_green_confirm", lambda _screen: None)
    monkeypatch.setattr(bot, "dismiss_unknown_popup", lambda _screen, allow_fallback=False: False)
    monkeypatch.setattr(bot, "human_sleep", lambda _seconds: None)
    monkeypatch.setattr(bot, "_lobby_side_tasks", lambda _screen: order.append("side_tasks") or False)
    monkeypatch.setattr(
        bot,
        "wait_for_scheduled_lobby_rest",
        lambda loops_done, on_rest_progress=None: order.append(("rest", loops_done)) or True,
    )
    monkeypatch.setattr(bot, "adb_tap", lambda *_args, **_kwargs: order.append("play"))

    def fake_find(screen, image, threshold=None):
        if image == bot.IMG_LOBBY_PLAY and str(screen).startswith("lobby"):
            return True, (1000, 660), 1.0
        if image == bot.IMG_BOOST_SCREEN and screen == "boost":
            return True, (500, 130), 1.0
        return False, None, 0.0

    monkeypatch.setattr(bot, "find_template", fake_find)
    monkeypatch.setattr(bot, "_find_optional", lambda *_args, **_kwargs: (False, None, 0.0))

    assert bot.ensure_on_boost_screen(rest_after_lobby=True, rest_loops_done=6) is True
    assert order == ["side_tasks", ("rest", 6), "play"]


def test_state_machine_schedules_each_screen_rest_on_next_lobby(monkeypatch):
    rest_flags = []
    stop = threading.Event()
    monkeypatch.setattr(bot, "STOP_FLAG", stop)
    monkeypatch.setattr(bot, "_require_runtime_license", lambda: True)
    monkeypatch.setitem(bot.SETTINGS, "loop_rest_enabled", True)
    monkeypatch.setitem(bot.SETTINGS, "loop_rest_every", 2)
    monkeypatch.setitem(bot.SETTINGS, "loop_rest_minutes", 5)

    def fake_reroll(rest_after_lobby=False, rest_loops_done=0, on_rest_progress=None):
        rest_flags.append((rest_after_lobby, rest_loops_done))
        return bot.State.RUN

    monkeypatch.setattr(bot, "state_reroll", fake_reroll)
    monkeypatch.setattr(bot, "state_run", lambda: bot.State.RESULT)
    monkeypatch.setattr(bot, "state_result", lambda: bot.State.REROLL)

    bot.run_state_machine(max_loops=3)

    assert rest_flags == [(False, 0), (False, 0), (True, 2)]
