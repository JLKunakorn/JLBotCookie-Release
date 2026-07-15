import json

import pytest

import notification_settings as settings
import premium_notifier


def _plain_store(monkeypatch, tmp_path):
    path = tmp_path / "notification_settings.dat"
    monkeypatch.setattr(settings, "_store_path", lambda: path)
    monkeypatch.setattr(settings, "_protect", lambda value: b"test:" + value)
    monkeypatch.setattr(settings, "_unprotect", lambda value: value.removeprefix(b"test:"))
    return path


def test_notification_settings_round_trip_is_encrypted_store(monkeypatch, tmp_path):
    path = _plain_store(monkeypatch, tmp_path)
    saved = settings.save_settings(
        {
            "mode": "custom",
            "webhook_url": "https://discord.com/api/webhooks/123456/token_value",
            "every_n_loops": 5,
            "notify_start": True,
            "notify_loop": True,
            "notify_stop": False,
        }
    )

    assert saved["every_n_loops"] == 5
    assert path.read_bytes().startswith(b"test:")
    assert settings.load_settings() == saved


def test_removed_store_mode_falls_back_to_off():
    assert settings.normalize_settings({"mode": "store"})["mode"] == settings.MODE_OFF


@pytest.mark.parametrize(
    "url",
    [
        "http://discord.com/api/webhooks/123/token",
        "https://example.com/api/webhooks/123/token",
        "https://discord.com/channels/123/456",
        "https://discord.com/api/webhooks/123/token?wait=true",
    ],
)
def test_webhook_validator_rejects_non_discord_or_modified_urls(url):
    with pytest.raises(ValueError):
        settings.validate_webhook_url(url)


def test_loop_notifications_respect_every_n_loops(monkeypatch):
    notifier = premium_notifier.PremiumNotifier(
        {"mode": "custom", "webhook_url": "https://discord.com/api/webhooks/123/token", "every_n_loops": 3}
    )
    queued = []
    monkeypatch.setattr(notifier, "_enqueue", lambda event, callback=None: queued.append(event) or True)

    assert notifier.emit("loop", screen_label="MuMu 1", serial="127.0.0.1:16416", loops_done=1) is False
    assert notifier.emit("loop", screen_label="MuMu 1", serial="127.0.0.1:16416", loops_done=3) is True
    assert len(queued) == 1
    assert queued[0]["details"]["loops_done"] == 3
    assert queued[0]["screen_id"] != "127.0.0.1:16416"
    assert "license_key" not in queued[0]
    assert "discord_user_id" not in queued[0]


def test_discord_payload_is_structured_and_does_not_include_internal_logs():
    payload = premium_notifier.build_discord_payload(
        {
            "event_type": "loop",
            "screen_label": "MuMu 2",
            "occurred_at": 1_700_000_000,
            "details": {"loops_done": 4, "max_loops": 10, "coins": 1234, "total": 9999, "traceback": "SECRET"},
        }
    )
    raw = json.dumps(payload, ensure_ascii=False)

    assert "MuMu 2" in raw
    assert "1,234" in raw
    assert "9,999" in raw
    assert "SECRET" not in raw
    assert payload["allowed_mentions"] == {"parse": []}
