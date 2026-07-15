import bot
import premium_runtime as runtime


def test_lobby_side_tasks_run_relic_then_mail_and_log_skips(monkeypatch):
    first_screen = object()
    second_screen = object()
    calls = []
    lifecycle = []
    logs = []

    monkeypatch.setattr(bot, "ADB_DEVICE", "serial-a")
    monkeypatch.setattr(bot, "ADB_PATH", "test-adb.exe")
    monkeypatch.setitem(bot.SETTINGS, "use_relic", True)
    monkeypatch.setitem(bot.SETTINGS, "use_mail_lives", True)
    monkeypatch.setattr(bot, "MAIL_MIN_COUNT", 5)
    monkeypatch.setattr(bot, "LOG_CALLBACK", logs.append)
    monkeypatch.setattr(bot, "adb_screencap", lambda: second_screen)
    monkeypatch.setattr(
        bot.side_task_adb,
        "register_device_stop_event",
        lambda serial, event: lifecycle.append(("register", serial, event)),
    )
    monkeypatch.setattr(
        bot.side_task_adb,
        "unregister_device_stop_event",
        lambda serial, event: lifecycle.append(("unregister", serial, event)),
    )

    def fake_relic(serial, screen=None, stop_event=None, progress_callback=None, settings=None):
        calls.append(("relic", serial, screen, settings))
        return runtime.result(
            runtime.AutomationStatus.SUCCESS,
            serial,
            "Relic Claim skipped.",
            {"claimed": 0},
            {"skipped": True, "reason": "no_indicator"},
        )

    def fake_mail(serial, screen=None, stop_event=None, progress_callback=None, settings=None):
        calls.append(("mail_lives", serial, screen, settings))
        return runtime.result(
            runtime.AutomationStatus.SUCCESS,
            serial,
            "Mail Lives skipped because badge is below minimum.",
            {"received": 0, "badge": 2},
            {"skipped": True, "reason": "below_minimum", "minimum": 5},
        )

    monkeypatch.setattr(bot.relic_claim_bot, "maybe_collect_relic", fake_relic)
    monkeypatch.setattr(bot.mail_lives_bot, "maybe_collect_mail_lives", fake_mail)

    acted = bot._lobby_side_tasks(first_screen)

    assert acted is False
    assert [item[0] for item in calls] == ["relic", "mail_lives"]
    assert calls[0][2] is first_screen
    assert calls[1][2] is second_screen
    assert calls[1][3] == {"min_count": 5}
    assert lifecycle[0][:2] == ("register", "serial-a")
    assert lifecycle[-1][:2] == ("unregister", "serial-a")
    assert bot.side_task_adb.ADB_PATH == "test-adb.exe"
    assert any("reason=no_indicator" in line for line in logs)
    assert any("reason=below_minimum" in line for line in logs)


def test_lobby_side_tasks_reports_action_when_relic_runs(monkeypatch):
    monkeypatch.setattr(bot, "ADB_DEVICE", "serial-a")
    monkeypatch.setitem(bot.SETTINGS, "use_relic", True)
    monkeypatch.setitem(bot.SETTINGS, "use_mail_lives", False)
    monkeypatch.setattr(bot.side_task_adb, "register_device_stop_event", lambda *_args: None)
    monkeypatch.setattr(bot.side_task_adb, "unregister_device_stop_event", lambda *_args: None)
    monkeypatch.setattr(bot, "adb_screencap", lambda: object())
    monkeypatch.setattr(
        bot.relic_claim_bot,
        "maybe_collect_relic",
        lambda serial, **_kwargs: runtime.result(
            runtime.AutomationStatus.SUCCESS,
            serial,
            "Relic Claim completed.",
            {"claimed": 1},
        ),
    )

    assert bot._lobby_side_tasks(object()) is True


def test_lobby_side_tasks_do_nothing_when_both_toggles_are_off(monkeypatch):
    monkeypatch.setitem(bot.SETTINGS, "use_relic", False)
    monkeypatch.setitem(bot.SETTINGS, "use_mail_lives", False)
    monkeypatch.setattr(bot, "ADB_DEVICE", "serial-a")
    assert bot._lobby_side_tasks(object()) is False
