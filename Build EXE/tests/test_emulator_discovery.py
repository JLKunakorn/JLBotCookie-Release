import bot


def test_profile_filter_separates_ldplayer_and_mumu_ports():
    assert bot._serial_matches_profile("emulator-5554", "LDPlayer") is True
    assert bot._serial_matches_profile("127.0.0.1:5555", "LDPlayer") is True
    assert bot._serial_matches_profile("127.0.0.1:16384", "LDPlayer") is False

    assert bot._serial_matches_profile("127.0.0.1:16384", "MuMu") is True
    assert bot._serial_matches_profile("127.0.0.1:16416", "MuMu") is True
    assert bot._serial_matches_profile("emulator-5554", "MuMu") is False
    assert bot._serial_slot_id("emulator-5556", "LDPlayer") == bot._serial_slot_id(
        "127.0.0.1:5557", "LDPlayer"
    )


def test_list_instances_excludes_cross_brand_and_stale_devices(monkeypatch):
    devices = [
        "emulator-5554",
        "127.0.0.1:5555",
        "127.0.0.1:16384",
        "127.0.0.1:5557",
    ]
    monkeypatch.setattr(bot, "adb_path_for_emu", lambda _emu: "adb.exe")
    monkeypatch.setattr(bot, "_ld_running_indices", lambda: None)
    monkeypatch.setattr(bot, "_mumu_running_ports", lambda: None)
    monkeypatch.setattr(bot, "_port_open", lambda _port: False)
    monkeypatch.setattr(bot, "_list_online_devices_with_adb", lambda _adb: list(devices))
    monkeypatch.setattr(
        bot,
        "_device_has_framebuffer",
        lambda _adb, serial: serial != "127.0.0.1:5557",
    )

    assert bot.list_emu_instances("LDPlayer") == ["127.0.0.1:5555"]
    assert bot.list_emu_instances("MuMu") == ["127.0.0.1:16384"]


def test_emulator_managers_are_authoritative(monkeypatch):
    monkeypatch.setattr(bot, "adb_path_for_emu", lambda _emu: "adb.exe")
    monkeypatch.setattr(bot, "_port_open", lambda _port: True)
    monkeypatch.setattr(bot, "_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "_device_has_framebuffer", lambda _adb, _serial: True)
    monkeypatch.setattr(
        bot,
        "_list_online_devices_with_adb",
        lambda _adb: ["127.0.0.1:5557", "127.0.0.1:5559", "127.0.0.1:16416"],
    )

    monkeypatch.setattr(bot, "_ld_running_indices", lambda: [])
    assert bot.list_emu_instances("LDPlayer") == []

    monkeypatch.setattr(bot, "_ld_running_indices", lambda: [1])
    assert bot.list_emu_instances("LDPlayer") == ["emulator-5556"]

    monkeypatch.setattr(bot, "_mumu_running_ports", lambda: [16416, 16448])
    assert bot.list_emu_instances("MuMu") == ["127.0.0.1:16416", "127.0.0.1:16448"]


def test_combined_discovery_preserves_the_correct_adb_for_each_brand(monkeypatch):
    monkeypatch.setattr(
        bot,
        "adb_path_for_emu",
        lambda emu: {"LDPlayer": "ld-adb.exe", "MuMu": "mumu-adb.exe"}[emu],
    )
    monkeypatch.setattr(
        bot,
        "list_emu_instances",
        lambda emu: ["emulator-5554"] if emu == "LDPlayer" else ["127.0.0.1:16384"],
    )

    found = bot.discover_emu_instances("LDPlayer + MuMu")

    assert [(item["emu"], item["adb_path"]) for item in found] == [
        ("LDPlayer", "ld-adb.exe"),
        ("MuMu", "mumu-adb.exe"),
    ]
    assert found[0]["label"].startswith("LDPlayer-")
    assert found[1]["label"].startswith("MuMu-")
