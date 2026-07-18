"""Isolated AutoFarm worker used by the Premium multi-screen UI.

One process owns exactly one emulator serial and one license key. The key is
received over stdin so it never appears in the Windows process command line.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback


_WRITE_LOCK = threading.Lock()


def _emit(event: str, **payload) -> None:
    message = {"event": event, **payload}
    data = (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    with _WRITE_LOCK:
        os.write(1, data)


def _read_config() -> dict:
    line = sys.stdin.readline()
    if not line:
        raise RuntimeError("worker configuration was not provided")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise RuntimeError("worker configuration is invalid")
    return value


def _license_tier_allowed(info) -> bool:
    if not isinstance(info, dict):
        return False
    tier = str(info.get("tier") or "").lower()
    key_tier = str(info.get("key_tier") or "premium").lower()
    return tier in {"pro", "premium", "infinite"} and key_tier in {"premium", "promax"}


def run_worker(config: dict) -> int:
    import bot
    import license_core

    key = str(config.get("key") or "").strip()
    serial = str(config.get("serial") or "").strip()
    adb_path = str(config.get("adb_path") or "").strip()
    if not key or not serial or not adb_path:
        raise RuntimeError("key, serial, and adb_path are required")

    bot._builtin_print = lambda *args, **kwargs: None
    bot.STOP_FLAG.clear()
    bot.ADB_PATH = adb_path
    bot.ADB_DEVICE = serial
    bot.COIN_LOG_SCREEN = serial
    bot.CAPTCHA_COUNT = 0
    settings = config.get("settings")
    if isinstance(settings, dict):
        bot.SETTINGS.update(settings)
    try:
        bot.MAIL_MIN_COUNT = max(0, int(config.get("mail_min_count") or 0))
    except (TypeError, ValueError):
        bot.MAIL_MIN_COUNT = 0
    try:
        max_loops = max(0, int(config.get("max_loops") or 0))
    except (TypeError, ValueError):
        max_loops = 0

    bot.LOG_CALLBACK = lambda message: _emit("log", message=str(message))
    bot.COIN_CALLBACK = lambda coins, total: _emit("coin", coins=coins, total=total)
    bot.CAPTCHA_CALLBACK = lambda count: _emit("captcha", count=count)

    ok, info = license_core.check_screen_key(key, force_online=True)
    if not ok or not _license_tier_allowed(info):
        _emit("license", ok=False, message=str(info))
        return 3
    bot.set_license_context(info)
    _emit("license", ok=True)

    def listen_for_stop():
        for line in sys.stdin:
            try:
                command = json.loads(line)
            except Exception:
                continue
            if isinstance(command, dict) and command.get("command") == "stop":
                bot.STOP_FLAG.set()
                break

    def license_heartbeat():
        while not bot.STOP_FLAG.wait(600):
            heartbeat_ok, heartbeat_info = license_core.check_screen_key(key, force_online=True)
            if heartbeat_ok and _license_tier_allowed(heartbeat_info):
                bot.set_license_context(heartbeat_info)
                continue
            _emit("license", ok=False, message=str(heartbeat_info))
            bot.STOP_FLAG.set()
            break

    threading.Thread(target=listen_for_stop, name="premium-worker-stop", daemon=True).start()
    threading.Thread(target=license_heartbeat, name="premium-worker-license", daemon=True).start()

    if not bot.check_connection():
        _emit("error", message="ADB connection failed for this screen")
        return 4
    _emit("ready", serial=serial)

    def on_loop_done(loops_done):
        _emit("loop", loops_done=loops_done, max_loops=max_loops)

    def on_rest_progress(**payload):
        _emit("rest", **payload)

    bot.run_state_machine(
        max_loops=max_loops,
        on_loop_done=on_loop_done,
        on_rest_progress=on_rest_progress,
    )
    return 0


def main() -> None:
    exit_code = 1
    try:
        exit_code = run_worker(_read_config())
    except Exception as exc:
        payload = {"message": str(exc)}
        if not getattr(sys, "frozen", False):
            payload["traceback"] = traceback.format_exc()
        _emit("error", **payload)
    finally:
        _emit("finished", exit_code=exit_code)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
