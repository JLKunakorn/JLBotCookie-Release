import json

import pytest

import license_core
import screen_license_store as store


def _plain_store(monkeypatch, tmp_path):
    path = tmp_path / "screen_keys.dat"
    monkeypatch.setattr(store, "_store_path", lambda: path)
    monkeypatch.setattr(store, "_protect", lambda value: b"test:" + value)
    monkeypatch.setattr(store, "_unprotect", lambda value: value.removeprefix(b"test:"))
    return path


def test_extra_keys_are_separate_masked_and_removable(monkeypatch, tmp_path):
    path = _plain_store(monkeypatch, tmp_path)

    first = store.add_key("JL-EXTRA-0001", primary_key="JL-PRIMARY-0001")
    second = store.add_key("JL-EXTRA-0002", primary_key="JL-PRIMARY-0001")

    assert path.exists()
    assert [item["key"] for item in store.load_keys()] == ["JL-EXTRA-0001", "JL-EXTRA-0002"]
    assert "EXTRA" not in store.mask_key("JL-EXTRA-0001")
    assert store.remove_key(first["id"]) is True
    assert [item["id"] for item in store.load_keys()] == [second["id"]]


def test_extra_key_rejects_primary_and_duplicates(monkeypatch, tmp_path):
    _plain_store(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="primary"):
        store.add_key("JL-SAME", primary_key="JL-SAME")
    store.add_key("JL-EXTRA", primary_key="JL-PRIMARY")
    with pytest.raises(ValueError, match="already"):
        store.add_key("JL-EXTRA", primary_key="JL-PRIMARY")


def test_screen_verification_does_not_replace_primary_state(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    license_core._save_state({"key": "JL-PRIMARY", "marker": "keep"})
    payload = {
        "ok": True,
        "hwid": license_core.get_hwid(),
        "tier": "pro",
        "key_tier": "premium",
        "token_exp": 4_102_444_800,
        "exp": 4_102_444_800,
    }
    response = {"signed": True}
    monkeypatch.setattr(license_core, "is_enabled", lambda: True)
    monkeypatch.setattr(license_core, "is_configured", lambda: True)
    monkeypatch.setattr(
        license_core,
        "_load_config",
        lambda: {"api_url": "https://license.invalid", "public_key_hex": "x", "request_timeout_seconds": 1},
    )
    monkeypatch.setattr(license_core, "_post_json", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(license_core, "_verify_signed_response", lambda resp, _cfg: payload if resp is response else None)

    ok, info = license_core.verify_screen_key("JL-EXTRA")

    assert ok is True
    assert info["key_tier"] == "premium"
    assert license_core.get_saved_key() == "JL-PRIMARY"
    assert license_core._load_state()["marker"] == "keep"
    assert license_core._screen_cache_path("JL-EXTRA").exists()
