import json
import os
import queue
import threading

import cv2
import numpy as np

import adb_core
import premium_ocr
import premium_runtime as runtime


ROOT = os.path.dirname(os.path.abspath(__file__))
RULES_FILE = os.path.join(ROOT, "rules.json")
TEMPLATE_DIR = os.path.join(ROOT, "templates")

MAIL_BADGE_OFFSET = (10, -52, 72, -8)
MAIL_CONFIRM_MAX = 320
MAIL_PROGRESS_BOX = (400, 255, 880, 320)
MAIL_PROGRESS_MIN = 6.0
STUCK_LIMIT = 4
CLEANUP_LIMIT = 8
GREEN_THRESHOLD = 0.5

TAP_REGIONS = {
    "mailbox": (680, 667, 17, 17),
    "lives_tab": (624, 137, 17, 17),
    "quick_receive": (629, 602, 17, 17),
    "confirm": (785, 450, 17, 17),
    "done": (632, 450, 17, 17),
    "close": (1121, 80, 17, 17),
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
    found = score >= float(rule.get("threshold", 0.8))
    tap = (sx1 + loc[0] + template.shape[1] // 2, sy1 + loc[1] + template.shape[0] // 2)
    return found, float(score), tap


def _find(screen, rules, name):
    return match_rule(screen, rules[name])


def _capture(serial):
    return adb_core.adb_screencap(serial)


def _tap(serial, name, stop_event=None, wait_after=0.0, wait_jitter=0.0):
    return runtime.human_tap_region(
        serial,
        TAP_REGIONS[name],
        stop_event=stop_event,
        wait_after=wait_after,
        wait_jitter=wait_jitter,
    )


def _emit(progress_callback, serial, step, counts=None, error=None):
    retry = counts.get("received") if counts else None
    runtime.emit_progress(progress_callback, serial, step, retry=retry, error=error)


def _green_ratio(screen, x, y, half=28):
    if screen is None:
        return 0.0
    h, w = screen.shape[:2]
    x1, x2 = max(0, x - half), min(w, x + half)
    y1, y2 = max(0, y - half), min(h, y + half)
    roi = screen[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (35, 90, 90), (75, 255, 255))
    return float(mask.mean()) / 255.0


def _region_gray(screen, box):
    if screen is None:
        return None
    x0, y0, x1, y1 = box
    h, w = screen.shape[:2]
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    roi = screen[y0:y1, x0:x1]
    if roi.size == 0:
        return None
    return cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32)


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


def _lobby_ready(screen, rules):
    found, _, pos = _find(screen, rules, "lobby_play")
    return found and not _play_is_dim(screen, pos)


def _mail_badge_crop(screen, mail_pos):
    dx1, dy1, dx2, dy2 = MAIL_BADGE_OFFSET
    x0, y0 = mail_pos[0] + dx1, mail_pos[1] + dy1
    x1, y1 = mail_pos[0] + dx2, mail_pos[1] + dy2
    h, w = screen.shape[:2]
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    return screen[y0:y1, x0:x1]


def read_mail_badge(screen, rules=None):
    if screen is None:
        return premium_ocr.OcrResult(None, profile=premium_ocr.PROFILE_MAIL_BADGE, reason="no_screen")
    rules = rules or load_rules()
    found, _score, pos = _find(screen, rules, "mail_icon")
    if not found:
        pos = (675, 678)
    crop = _mail_badge_crop(screen, pos)
    if crop is None or crop.size == 0:
        return premium_ocr.OcrResult(None, profile=premium_ocr.PROFILE_MAIL_BADGE, reason="invalid_badge_roi")
    return premium_ocr.read_mail_badge_crop(crop)


def _cleanup_to_lobby(serial, rules, stop_event=None, progress_callback=None):
    for _ in range(CLEANUP_LIMIT):
        if runtime.is_cancelled(stop_event):
            return runtime.AutomationStatus.CANCELLED
        screen = _capture(serial)
        if _lobby_ready(screen, rules):
            return runtime.AutomationStatus.SUCCESS
        if screen is not None and _find(screen, rules, "mailbox_title")[0]:
            _tap(serial, "close", stop_event, 1.0, 0.2)
            _emit(progress_callback, serial, "Mail Lives: close mailbox")
        else:
            _tap(serial, "close", stop_event, 0.8, 0.2)
    return runtime.AutomationStatus.TIMEOUT


def run_mail_lives(serial, stop_event=None, progress_callback=None, settings=None):
    rules = load_rules()
    settings = settings or {}
    counts = {"received": 0, "badge": 0}

    _emit(progress_callback, serial, "Mail Lives: check lobby", counts)
    screen = _capture(serial)
    if not _lobby_ready(screen, rules):
        return runtime.result(
            runtime.AutomationStatus.NOT_READY,
            serial,
            "Mail Lives requires the current account to be on the lobby screen.",
            counts,
        )

    badge = read_mail_badge(screen, rules)
    if badge.value is None:
        return runtime.result(
            runtime.AutomationStatus.SUCCESS,
            serial,
            "Mail Lives skipped because the mail badge was not readable.",
            counts,
            {"skipped": True, "reason": badge.reason, "confidence": badge.confidence, "raw_digits": badge.raw_digits},
        )
    counts["badge"] = badge.value
    minimum = int(settings.get("min_count", 0))
    if badge.value < minimum:
        return runtime.result(
            runtime.AutomationStatus.SUCCESS,
            serial,
            "Mail Lives skipped because the badge count is below the minimum.",
            counts,
            {"skipped": True, "reason": "below_minimum", "minimum": minimum},
        )

    _emit(progress_callback, serial, "Mail Lives: open mailbox", counts)
    _tap(serial, "mailbox", stop_event, 1.9, 0.35)
    if runtime.is_cancelled(stop_event):
        return runtime.result(runtime.AutomationStatus.CANCELLED, serial, "Mail Lives cancelled.", counts)

    screen = _capture(serial)
    if not _find(screen, rules, "mailbox_title")[0]:
        cleanup_status = _cleanup_to_lobby(serial, rules, stop_event, progress_callback)
        return runtime.result(
            runtime.AutomationStatus.TARGET_NOT_FOUND,
            serial,
            "Mailbox title was not found after opening.",
            counts,
            {"cleanup_status": cleanup_status},
        )

    _tap(serial, "lives_tab", stop_event, 1.0, 0.25)
    _tap(serial, "quick_receive", stop_event, 1.3, 0.3)

    stuck = 0
    last_region = None
    final_status = runtime.AutomationStatus.SUCCESS
    message = "Mail Lives completed."
    for _ in range(MAIL_CONFIRM_MAX):
        if runtime.is_cancelled(stop_event):
            final_status = runtime.AutomationStatus.CANCELLED
            message = "Mail Lives cancelled."
            break
        screen = _capture(serial)
        region = _region_gray(screen, MAIL_PROGRESS_BOX)
        if region is not None and last_region is not None and region.shape == last_region.shape:
            if float(np.mean(np.abs(region - last_region))) < MAIL_PROGRESS_MIN:
                stuck += 1
                if stuck >= STUCK_LIMIT:
                    message = "Mail Lives stopped because the progress region stopped changing."
                    break
            else:
                stuck = 0
        else:
            stuck = 0
        last_region = region

        if _green_ratio(screen, 793, 458) > GREEN_THRESHOLD:
            _emit(progress_callback, serial, "Mail Lives: confirm", counts)
            _tap(serial, "confirm", stop_event, 1.1, 0.35)
            counts["received"] += 1
            continue
        if _green_ratio(screen, 640, 458) > GREEN_THRESHOLD:
            _tap(serial, "done", stop_event, 1.0, 0.25)
            message = "Mail Lives reached done confirmation."
            break
        if counts["received"] == 0:
            message = "Mail Lives found no heart mails to receive."
        break
    else:
        final_status = runtime.AutomationStatus.TIMEOUT
        message = "Mail Lives reached the confirm safety cap."

    cleanup_status = _cleanup_to_lobby(serial, rules, stop_event, progress_callback)
    if cleanup_status == runtime.AutomationStatus.CANCELLED:
        final_status = runtime.AutomationStatus.CANCELLED
        message = "Mail Lives cancelled."
    return runtime.result(final_status, serial, message, counts, {"cleanup_status": cleanup_status})


def maybe_collect_mail_lives(serial, screen=None, stop_event=None, progress_callback=None, settings=None):
    rules = load_rules()
    current_screen = screen if screen is not None else _capture(serial)
    if not _lobby_ready(current_screen, rules):
        return runtime.result(
            runtime.AutomationStatus.NOT_READY,
            serial,
            "Mail Lives skipped because lobby is not ready.",
            {"received": 0, "badge": 0},
            {"skipped": True, "reason": "not_lobby"},
        )
    badge = read_mail_badge(current_screen, rules)
    if badge.value is None:
        return runtime.result(
            runtime.AutomationStatus.SUCCESS,
            serial,
            "Mail Lives skipped because OCR was not confident.",
            {"received": 0, "badge": 0},
            {"skipped": True, "reason": badge.reason, "confidence": badge.confidence, "raw_digits": badge.raw_digits},
        )
    minimum = int((settings or {}).get("min_count", 0))
    if badge.value < minimum:
        return runtime.result(
            runtime.AutomationStatus.SUCCESS,
            serial,
            "Mail Lives skipped because badge is below minimum.",
            {"received": 0, "badge": badge.value},
            {"skipped": True, "reason": "below_minimum", "minimum": minimum},
        )
    return run_mail_lives(serial, stop_event=stop_event, progress_callback=progress_callback, settings=settings)


def run_parallel_mail_lives(devices, stop_event=None, progress_callback=None, settings=None):
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
                result = run_mail_lives(serial, stop_event=stop_event, progress_callback=progress_callback, settings=settings)
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
