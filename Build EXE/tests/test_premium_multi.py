import json
import queue
import threading

import bot
import license_core
import premium_multi


class _FakeStdout:
    def __init__(self):
        self.items = queue.Queue()

    def __iter__(self):
        while True:
            item = self.items.get(timeout=2)
            if item is None:
                return
            yield item


class _FakeStdin:
    def __init__(self):
        self.lines = []

    def write(self, value):
        self.lines.append(value)

    def flush(self):
        return None


class _FakeProcess:
    def __init__(self):
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout()
        self.code = None

    def poll(self):
        return self.code

    def wait(self):
        if self.code is None:
            self.code = 0
        return self.code

    def terminate(self):
        if self.code is None:
            self.code = -15
            self.stdout.items.put(None)


class _PopenFactory:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kwargs):
        process = _FakeProcess()
        self.calls.append((list(argv), kwargs, process))
        return process


def test_manager_starts_two_isolated_screens_and_keys_are_not_in_argv():
    factory = _PopenFactory()
    manager = premium_multi.MultiFarmManager(popen_factory=factory)

    manager.start(
        "127.0.0.1:16384",
        "JL-KEY-ONE",
        "adb.exe",
        {"use_jump": False, "run_mode": "slide", "slide_delay_min": 0.4, "slide_delay_max": 0.8},
    )
    manager.start(
        "127.0.0.1:16416",
        "JL-KEY-TWO",
        "adb.exe",
        {"use_jump": False, "run_mode": "none"},
    )

    assert len(factory.calls) == 2
    assert all("JL-KEY" not in " ".join(call[0]) for call in factory.calls)
    first_config = json.loads(factory.calls[0][2].stdin.lines[0])
    second_config = json.loads(factory.calls[1][2].stdin.lines[0])
    assert first_config["key"] == "JL-KEY-ONE"
    assert second_config["key"] == "JL-KEY-TWO"
    assert first_config["serial"] != second_config["serial"]
    assert first_config["settings"]["run_mode"] == "slide"
    assert first_config["settings"]["slide_delay_min"] == 0.4
    assert second_config["settings"]["run_mode"] == "none"

    assert manager.stop("127.0.0.1:16384", force_after=0) is True
    assert json.loads(factory.calls[0][2].stdin.lines[-1]) == {"command": "stop"}
    assert len(factory.calls[1][2].stdin.lines) == 1
    manager.terminate_all()


def test_coin_events_are_routed_to_the_correct_screen_only():
    factory = _PopenFactory()
    received = []
    both_received = threading.Event()

    def on_event(serial, event):
        if event.get("event") == "coin":
            received.append((serial, event["coins"], event["total"]))
            if len(received) == 2:
                both_received.set()

    manager = premium_multi.MultiFarmManager(event_callback=on_event, popen_factory=factory)
    manager.start("screen-1", "JL-KEY-ONE", "adb-1.exe", {})
    manager.start("screen-2", "JL-KEY-TWO", "adb-2.exe", {})
    factory.calls[0][2].stdout.items.put(json.dumps({"event": "coin", "coins": 100, "total": 100}) + "\n")
    factory.calls[1][2].stdout.items.put(json.dumps({"event": "coin", "coins": 250, "total": 900}) + "\n")

    assert both_received.wait(1.0) is True
    assert ("screen-1", 100, 100) in received
    assert ("screen-2", 250, 900) in received
    manager.terminate_all()


def test_bot_accepts_preverified_worker_context_without_primary_lookup(monkeypatch):
    monkeypatch.setattr(license_core, "is_enabled", lambda: True)
    monkeypatch.setattr(
        license_core,
        "check_license",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("primary key must not be checked")),
    )
    bot.set_license_context({"tier": "pro", "key_tier": "premium"})
    try:
        assert bot._require_runtime_license() is True
    finally:
        bot.clear_license_context()


def test_coin_log_directory_is_scoped_to_each_worker_screen(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "_writable_dir", lambda: str(tmp_path))
    monkeypatch.setattr(bot, "COIN_LOG_SCREEN", "127.0.0.1:16416")
    first = bot._coin_log_dir()
    monkeypatch.setattr(bot, "COIN_LOG_SCREEN", "127.0.0.1:16448")
    second = bot._coin_log_dir()

    assert first != second
    assert first.endswith("coin_logs\\127.0.0.1_16416")
    assert second.endswith("coin_logs\\127.0.0.1_16448")
