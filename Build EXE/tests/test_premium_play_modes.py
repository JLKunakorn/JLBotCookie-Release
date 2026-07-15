import pytest

import bot
import JLmain


def test_delay_parser_accepts_one_value_or_random_range():
    assert JLmain._parse_delay_range("0.5", "delay") == (0.5, 0.5)
    assert JLmain._parse_delay_range("0.14-0.72", "delay") == (0.14, 0.72)
    assert JLmain._parse_delay_range("0,2–0,8", "delay") == (0.2, 0.8)


@pytest.mark.parametrize("value", ["", "fast", "0.8-0.2", "0.01", "1-20"])
def test_delay_parser_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        JLmain._parse_delay_range(value, "delay")


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        ({"run_mode": "jump"}, "jump"),
        ({"run_mode": "slide"}, "slide"),
        ({"run_mode": "jump_slide"}, "jump_slide"),
        ({"run_mode": "none"}, "none"),
        ({"run_mode": "invalid", "use_jump": False}, "none"),
    ],
)
def test_configured_run_mode(settings, expected):
    assert bot.configured_run_mode(settings) == expected


def test_jump_and_slide_delays_are_independent():
    settings = {
        "jump_delay_min": 0.1,
        "jump_delay_max": 0.2,
        "slide_delay_min": 0.8,
        "slide_delay_max": 0.9,
    }
    assert bot.action_delay_range("jump", settings) == (0.1, 0.2)
    assert bot.action_delay_range("slide", settings) == (0.8, 0.9)


def test_perform_run_action_supports_all_action_modes(monkeypatch):
    actions = []
    monkeypatch.setattr(bot, "_jump_point", lambda: (10, 20))
    monkeypatch.setattr(bot, "adb_tap", lambda *args, **kwargs: actions.append(("jump", args, kwargs)))
    monkeypatch.setattr(bot, "adb_slide", lambda: actions.append(("slide",)))

    assert bot.perform_run_action("jump") == "jump"
    assert bot.perform_run_action("slide") == "slide"
    monkeypatch.setattr(bot.random, "random", lambda: 0.1)
    assert bot.perform_run_action("jump_slide") == "jump"
    monkeypatch.setattr(bot.random, "random", lambda: 0.9)
    assert bot.perform_run_action("jump_slide") == "slide"

    assert [item[0] for item in actions] == ["jump", "slide", "jump", "slide"]
