import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot


def test_bundled_adb_is_preferred_over_emulator_install(monkeypatch):
    monkeypatch.setattr(bot, "_bundled_adb", lambda: "bundled-adb.exe")
    monkeypatch.setattr(bot.os.path, "exists", lambda path: path == "bundled-adb.exe")
    monkeypatch.setitem(
        bot.EMU_PROFILES,
        "LDPlayer",
        {"find_adb": lambda: "emulator-adb.exe", "ports": [5555]},
    )

    assert bot.adb_path_for_emu("LDPlayer") == "bundled-adb.exe"


def test_profile_filter_separates_ldplayer_and_mumu_ports():
    assert bot._serial_matches_profile("emulator-5554", "LDPlayer") is True
    assert bot._serial_matches_profile("127.0.0.1:5555", "LDPlayer") is True
    assert bot._serial_matches_profile("127.0.0.1:16384", "LDPlayer") is False

    assert bot._serial_matches_profile("127.0.0.1:16384", "MuMu") is True
    assert bot._serial_matches_profile("127.0.0.1:16416", "MuMu") is True
    assert bot._serial_matches_profile("127.0.0.1:7555", "MuMu") is True
    assert bot._serial_matches_profile("emulator-5554", "MuMu") is False
    assert bot._serial_slot_id("emulator-5556", "LDPlayer") == bot._serial_slot_id(
        "127.0.0.1:5557", "LDPlayer"
    )


def test_mumu_executables_are_found_in_unknown_future_folder(monkeypatch, tmp_path):
    install = tmp_path / "Program Files" / "Netease" / "MuMu Player 15"
    manager = install / "nx_main" / "MuMuManager.exe"
    adb = install / "nx_device" / "15.0" / "shell" / "adb.exe"
    manager.parent.mkdir(parents=True)
    adb.parent.mkdir(parents=True)
    manager.touch()
    adb.touch()

    monkeypatch.setattr(bot, "_iter_drives", lambda: [str(tmp_path)])

    assert Path(bot.find_mumu_manager()) == manager
    assert Path(bot.find_mumu_adb()) == adb


def test_ldplayer_executables_are_found_in_unknown_future_folder(monkeypatch, tmp_path):
    install = tmp_path / "LDPlayer" / "LDPlayer15"
    adb = install / "adb.exe"
    console = install / "ldconsole.exe"
    install.mkdir(parents=True)
    adb.touch()
    console.touch()

    monkeypatch.setattr(bot, "_iter_drives", lambda: [str(tmp_path)])

    assert Path(bot.find_ld_adb()) == adb
    assert Path(bot.find_ld_console()) == console


def test_list_instances_uses_adb_devices_and_deduplicates_aliases(monkeypatch):
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
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("framebuffer must not gate discovery")),
    )

    assert bot.list_emu_instances("LDPlayer") == ["127.0.0.1:5555", "127.0.0.1:5557"]
    assert bot.list_emu_instances("MuMu") == ["127.0.0.1:16384"]


def test_unavailable_manager_falls_back_to_adb_devices(monkeypatch):
    monkeypatch.setattr(bot, "adb_path_for_emu", lambda _emu: "adb.exe")
    monkeypatch.setattr(bot, "_port_open", lambda _port: True)
    monkeypatch.setattr(bot, "_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bot,
        "_list_online_devices_with_adb",
        lambda _adb: ["127.0.0.1:5557", "127.0.0.1:5559", "127.0.0.1:16416"],
    )

    monkeypatch.setattr(bot, "_ld_running_indices", lambda: None)
    assert bot.list_emu_instances("LDPlayer") == ["127.0.0.1:5557", "127.0.0.1:5559"]

    monkeypatch.setattr(bot, "_ld_running_indices", lambda: [1])
    assert bot.list_emu_instances("LDPlayer") == ["127.0.0.1:5557"]

    monkeypatch.setattr(bot, "_mumu_running_ports", lambda: [16416, 16448])
    assert bot.list_emu_instances("MuMu") == ["127.0.0.1:16416"]


def test_valid_empty_manager_result_rejects_cross_brand_aliases(monkeypatch):
    monkeypatch.setattr(bot, "adb_path_for_emu", lambda _emu: "adb.exe")
    monkeypatch.setattr(bot, "_ld_running_indices", lambda: [])
    monkeypatch.setattr(bot, "_mumu_running_ports", lambda: [])
    monkeypatch.setattr(bot, "_list_online_devices_with_adb", lambda _adb: ["127.0.0.1:5559"])

    assert bot.list_emu_instances("LDPlayer") == []
    assert bot.list_emu_instances("MuMu") == []


def test_manager_parsers_distinguish_invalid_output_from_no_running_instances(monkeypatch):
    monkeypatch.setattr(bot, "find_ld_console", lambda: "ldconsole.exe")
    monkeypatch.setattr(bot, "_run", lambda *_args, **_kwargs: SimpleNamespace(stdout=b"invalid"))
    assert bot._ld_running_indices() is None

    stopped = b"0,LDPlayer,0,0,0,0,0,1280,720,320\n"
    monkeypatch.setattr(bot, "_run", lambda *_args, **_kwargs: SimpleNamespace(stdout=stopped))
    assert bot._ld_running_indices() == []

    running = b"2,LDPlayer,0,0,1,1234,4321,1280,720,320\n"
    monkeypatch.setattr(bot, "_run", lambda *_args, **_kwargs: SimpleNamespace(stdout=running))
    assert bot._ld_running_indices() == [2]

    monkeypatch.setattr(bot, "find_mumu_manager", lambda: "MuMuManager.exe")
    monkeypatch.setattr(bot, "_run", lambda *_args, **_kwargs: SimpleNamespace(stdout=b"{}"))
    assert bot._mumu_running_ports() is None

    payload = {
        "0": {"is_process_started": False, "is_android_started": False, "adb_port": 16416},
        "1": {"is_process_started": True, "is_android_started": True, "adb_port": 16448},
    }
    raw = json.dumps(payload).encode("utf-8")
    monkeypatch.setattr(bot, "_run", lambda *_args, **_kwargs: SimpleNamespace(stdout=raw))
    assert bot._mumu_running_ports() == [16448]


def test_mumu_port_falls_back_to_index_when_adb_port_is_missing(monkeypatch):
    """MuMuManager on the Android 15 "AD15" line drops adb_port from info -v all
    (observed live on a real upgraded MuMu install) but still reports index."""
    monkeypatch.setattr(bot, "find_mumu_manager", lambda: "MuMuManager.exe")
    payload = {
        "3": {
            "index": "3",
            "android_version": "12.0",
            "is_process_started": True,
            "is_android_started": True,
        },
        "4": {
            "index": "4",
            "android_version": "15.0",
            "is_process_started": True,
            "is_android_started": True,
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    monkeypatch.setattr(bot, "_run", lambda *_args, **_kwargs: SimpleNamespace(stdout=raw))
    assert bot._mumu_running_ports() == [16480, 16512]


def test_manager_ports_extend_the_adb_scan_without_replacing_it(monkeypatch):
    monkeypatch.setattr(bot, "adb_path_for_emu", lambda _emu: "adb.exe")
    monkeypatch.setattr(bot, "_mumu_running_ports", lambda: [7555])
    monkeypatch.setattr(bot, "_port_open", lambda _port: False)
    monkeypatch.setattr(bot, "_list_online_devices_with_adb", lambda _adb: ["127.0.0.1:7555"])

    assert bot.list_emu_instances("MuMu") == ["127.0.0.1:7555"]


def test_mumu_7555_is_discovered_when_manager_is_unavailable(monkeypatch):
    monkeypatch.setattr(bot, "adb_path_for_emu", lambda _emu: "adb.exe")
    monkeypatch.setattr(bot, "_mumu_running_ports", lambda: None)
    monkeypatch.setattr(bot, "_port_open", lambda _port: False)
    monkeypatch.setattr(bot, "_list_online_devices_with_adb", lambda _adb: ["127.0.0.1:7555"])

    assert bot.list_emu_instances("MuMu") == ["127.0.0.1:7555"]


def test_empty_discovery_restarts_adb_and_retries_once(monkeypatch):
    scans = []
    commands = []

    monkeypatch.setattr(bot, "adb_path_for_emu", lambda _emu: "adb.exe")

    def fake_list(emu):
        scans.append(emu)
        return [] if len(scans) == 1 else ["127.0.0.1:16384"]

    monkeypatch.setattr(bot, "list_emu_instances", fake_list)
    monkeypatch.setattr(bot, "_run", lambda command, **_kwargs: commands.append(command))
    monkeypatch.setattr(bot.time, "sleep", lambda _seconds: None)

    found = bot.discover_emu_instances("MuMu")

    assert scans == ["MuMu", "MuMu"]
    assert commands == [["adb.exe", "kill-server"]]
    assert [(item["emu"], item["serial"]) for item in found] == [
        ("MuMu", "127.0.0.1:16384")
    ]


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


def test_combined_discovery_does_not_show_mumu_alias_as_ldplayer(monkeypatch):
    monkeypatch.setattr(bot, "adb_path_for_emu", lambda _emu: "bundled-adb.exe")
    monkeypatch.setattr(bot, "_ld_running_indices", lambda: [])
    monkeypatch.setattr(bot, "_mumu_running_ports", lambda: [16448])
    monkeypatch.setattr(bot, "_port_open", lambda _port: False)
    monkeypatch.setattr(
        bot,
        "_list_online_devices_with_adb",
        lambda _adb: ["127.0.0.1:5559", "127.0.0.1:16448"],
    )

    found = bot.discover_emu_instances("LDPlayer + MuMu")

    assert [(item["emu"], item["serial"]) for item in found] == [
        ("MuMu", "127.0.0.1:16448")
    ]
