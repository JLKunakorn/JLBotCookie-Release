import json
import os
import queue
import threading

import cv2
import numpy as np

import adb_core
import premium_runtime as runtime


ROOT = os.path.dirname(os.path.abspath(__file__))
RULES_FILE = os.path.join(ROOT, "rules.json")
TEMPLATE_DIR = os.path.join(ROOT, "templates")

RELIC_GET_POS = (530, 83)
RELIC_TAP_MAX = 8
RELIC_LOOP_MAX = RELIC_TAP_MAX * 2
GREEN_THRESHOLD = 0.5
CLEANUP_LIMIT = 8

TAP_REGIONS = {
    "open": (507, 92, 17, 17),
    "claim": (632, 568, 17, 17),
    "close": (1069, 147, 17, 17),
}

_TEMPLATE_CACHE = {}


def load_rules():
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        return {rule["name"]: rule for rule in json.load(f)}


def _template(rule):
    name = rule["name"]
    if name not in _TEMPLATE_CACHE:
        path = os.path.join(TEMPLATE_DIR, rule["template"])
        _TEMPLATE_CACHE[name] = cv2.imread(path, cv2.IMREAD_COLOR)
    return _TEMPLATE_CACHE[name]


def match_rule(screen, rule):
    template = _template(rule)
    if screen is None or template is None:
        return False, 0.0, None
    sx, sy, sw, sh = rule["scan"]
    h_scr, w_scr = screen.shape[:2]
    sx1 = max(0, min(w_scr - 1, sx))
    sy1 = max(0, min(h_scr - 1, sy))
    sx2 = max(0, min(w_scr, sx + sw))
    sy2 = max(0, min(h_scr, sy + sh))
    roi = screen[sy1:sy2, sx1:sx2]
    if roi.size == 0 or roi.shape[0] < template.shape[0] or roi.shape[1] < template.shape[1]:
        return False, 0.0, None
    result = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    found = score >= float(rule.get("threshold", 0.85))
    tap = (sx1 + loc[0] + template.shape[1] // 2, sy1 + loc[1] + template.shape[0] // 2)
    return found, float(score), tap


def _find(screen, rules, name):
    return match_rule(screen, rules[name])


def _green_ratio(screen, x, y, half=34):
    if screen is None:
        return 0.0
    h, w = screen.shape[:2]
    x1, x2 = max(0, x - half), min(w, x + half)
    y1, y2 = max(0, y - half), min(h, y + half)
    roi = screen[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    b, g, r = cv2.split(roi)
    mask = (g > 120) & (g > r * 1.18) & (g > b * 1.18)
    return float(np.count_nonzero(mask)) / float(mask.size)


def _play_is_dim(screen, pos):
    if screen is None or not pos:
        return False
    x, y = pos
    h, w = screen.shape[:2]
    x1, x2 = max(0, x - 40), min(w, x + 40)
    y1, y2 = max(0, y - 24), min(h, y + 24)
    roi = screen[y1:y2, x1:x2]
    if roi.size == 0:
        return False
    return float(np.mean(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY))) < 90.0


def _tap(serial, name, stop_event=None, wait_after=0.0, wait_jitter=0.0):
    return runtime.human_tap_region(
        serial,
        TAP_REGIONS[name],
        stop_event=stop_event,
        wait_after=wait_after,
        wait_jitter=wait_jitter,
    )


def _capture(serial):
    return adb_core.adb_screencap(serial)


def _emit(progress_callback, serial, step):
    runtime.emit_progress(progress_callback, serial, step)


def _indicator_ready(screen, rules):
    lobby_found, _, lobby_pos = _find(screen, rules, "lobby_play")
    if not lobby_found or _play_is_dim(screen, lobby_pos):
        return False, "not_lobby"
    indicator_found, _, indicator_pos = _find(screen, rules, "relic_get")
    if not indicator_found:
        return False, "no_indicator"
    if abs(indicator_pos[0] - RELIC_GET_POS[0]) > 40 or abs(indicator_pos[1] - RELIC_GET_POS[1]) > 40:
        return False, "indicator_position"
    return True, "ready"


def _cleanup_to_lobby(serial, rules, stop_event=None, progress_callback=None):
    for _ in range(CLEANUP_LIMIT):
        if runtime.is_cancelled(stop_event):
            return runtime.AutomationStatus.CANCELLED
        screen = _capture(serial)
        lobby_found, _, lobby_pos = _find(screen, rules, "lobby_play")
        if lobby_found and not _play_is_dim(screen, lobby_pos):
            return runtime.AutomationStatus.SUCCESS
        if _find(screen, rules, "relic_title")[0]:
            _tap(serial, "close", stop_event, 1.0, 0.2)
            _emit(progress_callback, serial, "Relic Claim: close relic")
        else:
            return runtime.AutomationStatus.TARGET_NOT_FOUND
    return runtime.AutomationStatus.TIMEOUT


def run_relic_claim(serial, stop_event=None, progress_callback=None, settings=None):
    rules = load_rules()
    counts = {"claimed": 0}

    _emit(progress_callback, serial, "Relic Claim: check indicator")
    screen = _capture(serial)
    ready, reason = _indicator_ready(screen, rules)
    if reason == "not_lobby":
        return runtime.result(
            runtime.AutomationStatus.NOT_READY,
            serial,
            "Relic Claim requires the current account to be on the lobby screen.",
            counts,
        )
    if not ready:
        return runtime.result(
            runtime.AutomationStatus.SUCCESS,
            serial,
            "No relic reward indicator is visible.",
            counts,
            {"skipped": True, "reason": reason},
        )

    _tap(serial, "open", stop_event, 2.0, 0.3)
    if runtime.is_cancelled(stop_event):
        return runtime.result(runtime.AutomationStatus.CANCELLED, serial, "cancelled", counts)

    screen = _capture(serial)
    if not _find(screen, rules, "relic_title")[0]:
        return runtime.result(
            runtime.AutomationStatus.TARGET_NOT_FOUND,
            serial,
            "Relic page title was not found after opening.",
            counts,
        )

    misses = 0
    final_status = runtime.AutomationStatus.SUCCESS
    message = "Relic Claim completed."
    for _ in range(RELIC_LOOP_MAX):
        if runtime.is_cancelled(stop_event):
            final_status = runtime.AutomationStatus.CANCELLED
            message = "Relic Claim cancelled."
            break
        screen = _capture(serial)
        if _green_ratio(screen, 640, 576) > GREEN_THRESHOLD:
            _emit(progress_callback, serial, "Relic Claim: claim reward")
            _tap(serial, "claim", stop_event, 1.1, 0.3)
            counts["claimed"] += 1
            misses = 0
            if counts["claimed"] >= RELIC_TAP_MAX:
                message = "Relic Claim reached claim safety cap."
                break
            continue
        misses += 1
        if misses >= (3 if counts["claimed"] == 0 else 4):
            break
        if not runtime.human_wait(0.9, 0.2, stop_event):
            final_status = runtime.AutomationStatus.CANCELLED
            message = "Relic Claim cancelled."
            break

    cleanup_status = _cleanup_to_lobby(serial, rules, stop_event, progress_callback)
    if cleanup_status == runtime.AutomationStatus.CANCELLED:
        final_status = runtime.AutomationStatus.CANCELLED
        message = "Relic Claim cancelled."
    return runtime.result(final_status, serial, message, counts)


def maybe_collect_relic(serial, screen=None, stop_event=None, progress_callback=None, settings=None):
    rules = load_rules()
    current_screen = screen if screen is not None else _capture(serial)
    ready, reason = _indicator_ready(current_screen, rules)
    if not ready:
        return runtime.result(
            runtime.AutomationStatus.SUCCESS if reason != "not_lobby" else runtime.AutomationStatus.NOT_READY,
            serial,
            "Relic Claim skipped.",
            {"claimed": 0},
            {"skipped": True, "reason": reason},
        )
    return run_relic_claim(serial, stop_event=stop_event, progress_callback=progress_callback, settings=settings)


def run_parallel_relic_claim(devices, stop_event=None, progress_callback=None, settings=None):
    jobs = queue.Queue()
    for serial in devices:
        jobs.put(serial)
    results = []
    errors = []
    lock = threading.Lock()

    def worker():
        while not runtime.is_cancelled(stop_event):
            try:
                serial = jobs.get_nowait()
            except queue.Empty:
                return
            try:
                result = run_relic_claim(serial, stop_event=stop_event, progress_callback=progress_callback, settings=settings)
                with lock:
                    results.append(result)
                    if not result.success and result.status != runtime.AutomationStatus.CANCELLED:
                        errors.append(f"{serial}: {result.status}")
            except Exception as exc:
                with lock:
                    errors.append(f"{serial}: {exc}")
            finally:
                jobs.task_done()

    threads = [threading.Thread(target=worker, daemon=True) for _ in devices]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return {"results": results, "errors": errors}
