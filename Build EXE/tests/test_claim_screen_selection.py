import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot
from JLmain import JLMainApp, MINT


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeLabel:
    def __init__(self):
        self.options = {}

    def configure(self, **options):
        self.options.update(options)


class FakeMultiFarm:
    def __init__(self, running_serials=None):
        self.running_serials = set(running_serials or [])

    def any_running(self):
        return bool(self.running_serials)

    def is_running(self, serial):
        return serial in self.running_serials


def make_app():
    app = JLMainApp.__new__(JLMainApp)
    app.screen_serials = ["127.0.0.1:5555", "127.0.0.1:16416"]
    app.instance_meta = {
        "127.0.0.1:5555": {
            "label": "LDPlayer-0 (5555)",
            "emu": "LDPlayer",
            "adb_path": "ld-adb.exe",
        },
        "127.0.0.1:16416": {
            "label": "MuMu-1 (16416)",
            "emu": "MuMu",
            "adb_path": "mumu-adb.exe",
        },
    }
    app.inst_serials = {
        "LDPlayer-0 (5555)": "127.0.0.1:5555",
        "MuMu-1 (16416)": "127.0.0.1:16416",
    }
    app.claim_screen_serial = ""
    app.adb_var = FakeVar("default-adb.exe")
    app.dev_var = FakeVar()
    app.inst_var = FakeVar()
    app.claim_screen_var = FakeVar()
    app.claim_screen_status_lbl = FakeLabel()
    app.status_var = FakeVar()
    app.status_lbl = FakeLabel()
    app.multi_farm = FakeMultiFarm()
    app.gift_running = False
    app.hearts_running = False
    app.tr_extract_running = False
    app.logs = []
    app._log = app.logs.append
    return app


def test_select_claim_screen_updates_adb_target_and_visible_label(monkeypatch):
    app = make_app()
    monkeypatch.setattr(bot, "ADB_DEVICE", None)
    monkeypatch.setattr(bot, "ADB_PATH", "old-adb.exe")

    assert app._set_claim_screen("127.0.0.1:16416") is True

    assert app.claim_screen_serial == "127.0.0.1:16416"
    assert app.dev_var.get() == "127.0.0.1:16416"
    assert app.adb_var.get() == "mumu-adb.exe"
    assert app.inst_var.get() == "MuMu-1 (16416)"
    assert bot.ADB_DEVICE == "127.0.0.1:16416"
    assert bot.ADB_PATH == "mumu-adb.exe"
    assert app.claim_screen_var.get() == "จอที่เลือก: เครื่อง 2  •  MuMu-1 (16416)"
    assert app.claim_screen_status_lbl.options["text_color"] == MINT
    assert "เครื่อง 2" in app.logs[-1]


def test_prepare_claim_start_reapplies_selected_screen(monkeypatch):
    app = make_app()
    app.claim_screen_serial = "127.0.0.1:5555"
    app.dev_var.set("127.0.0.1:16416")
    monkeypatch.setattr(bot, "ADB_DEVICE", "127.0.0.1:16416")
    monkeypatch.setattr(bot, "ADB_PATH", "mumu-adb.exe")

    assert app._prepare_claim_start(lambda: None) is True

    assert app.dev_var.get() == "127.0.0.1:5555"
    assert app.adb_var.get() == "ld-adb.exe"
    assert bot.ADB_DEVICE == "127.0.0.1:5555"
    assert bot.ADB_PATH == "ld-adb.exe"


def test_prepare_claim_start_opens_selector_when_no_screen_is_selected():
    app = make_app()
    pending = lambda: None
    captured = []
    app._show_claim_screen_popup = lambda on_selected=None: captured.append(on_selected)

    assert app._prepare_claim_start(pending) is False
    assert captured == [pending]
    assert app.claim_screen_var.get() == "ยังไม่ได้เลือกจอสำหรับ Claim item"


def test_prepare_claim_start_allows_autofarm_on_another_screen(monkeypatch):
    app = make_app()
    app.multi_farm = FakeMultiFarm(running_serials={"127.0.0.1:5555"})
    app.claim_screen_serial = "127.0.0.1:16416"
    monkeypatch.setattr(bot, "ADB_DEVICE", None)
    monkeypatch.setattr(bot, "ADB_PATH", "old-adb.exe")

    assert app._prepare_claim_start(lambda: None) is True
    assert bot.ADB_DEVICE == "127.0.0.1:16416"
    assert bot.ADB_PATH == "mumu-adb.exe"


def test_prepare_claim_start_reopens_selector_when_same_screen_runs_autofarm():
    app = make_app()
    app.multi_farm = FakeMultiFarm(running_serials={"127.0.0.1:5555"})
    app.claim_screen_serial = "127.0.0.1:5555"
    pending = lambda: None
    captured = []
    app._show_claim_screen_popup = lambda on_selected=None: captured.append(on_selected)

    assert app._prepare_claim_start(pending) is False
    assert app.claim_screen_serial == ""
    assert captured == [pending]
    assert "กรุณาเลือกจออื่น" in app.logs[-1]
