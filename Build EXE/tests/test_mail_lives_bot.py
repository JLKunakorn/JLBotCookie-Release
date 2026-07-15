import os
import sys
import threading

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import premium_ocr as ocr
import premium_runtime as runtime
from ClaimItems.MailLives import mail_lives_bot as mail


def _frame():
    return np.full((720, 1280, 3), 255, dtype=np.uint8)


def _paste_template(frame, root, name, x, y):
    tpl = cv2.imread(os.path.join(root, name), cv2.IMREAD_COLOR)
    h, w = tpl.shape[:2]
    frame[y:y + h, x:x + w] = tpl
    return frame


def _mail_template(name):
    return os.path.join(mail.TEMPLATE_DIR, name)


def _digit_template(digit):
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "dig", f"{digit}.png")
    return cv2.imread(path, cv2.IMREAD_GRAYSCALE)


def _badge_pill(value):
    digits = [str(ch) for ch in str(value)]
    width = len(digits) * ocr.DIGIT_SIZE[0] + max(0, len(digits) - 1) * 2 + 18
    height = ocr.DIGIT_SIZE[1] + 12
    crop = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.rectangle(crop, (2, 2), (width - 3, height - 3), (0, 0, 230), -1)
    x = 9
    for digit in digits:
        tpl = _digit_template(digit)
        mask = tpl > 32
        roi = crop[6:6 + ocr.DIGIT_SIZE[1], x:x + ocr.DIGIT_SIZE[0]]
        roi[mask] = (255, 255, 255)
        x += ocr.DIGIT_SIZE[0] + 2
    return crop


def _lobby(badge=None):
    frame = _paste_template(_frame(), mail.TEMPLATE_DIR, "lobby_play.png", 950, 630)
    frame = _paste_template(frame, mail.TEMPLATE_DIR, "mail_icon.png", 656, 656)
    if badge is not None:
        pill = _badge_pill(badge)
        x, y = 675 + mail.MAIL_BADGE_OFFSET[0], 678 + mail.MAIL_BADGE_OFFSET[1]
        frame[y:y + pill.shape[0], x:x + pill.shape[1]] = pill
    return frame


def _mailbox():
    return _paste_template(_frame(), mail.TEMPLATE_DIR, "mailbox_title.png", 520, 60)


def _green_popup(x, y):
    frame = _mailbox()
    frame[y - 30:y + 30, x - 30:x + 30] = (20, 220, 20)
    return frame


def _run_with_frames(monkeypatch, frames, settings=None, stop_event=None):
    taps = []
    events = []

    def fake_capture(_serial):
        if frames:
            return frames.pop(0)
        return _lobby()

    monkeypatch.setattr(mail, "_capture", fake_capture)
    monkeypatch.setattr(mail, "_tap", lambda serial, name, stop_event=None, wait_after=0.0, wait_jitter=0.0: taps.append(name))
    monkeypatch.setattr(mail.runtime, "human_wait", lambda seconds, jitter=0.0, stop_event=None, rng=None: not runtime.is_cancelled(stop_event))
    result = mail.run_mail_lives(
        "serial-a",
        stop_event=stop_event,
        progress_callback=events.append,
        settings=settings or {"min_count": 1},
    )
    return result, taps, events


def test_read_mail_badge_from_lobby():
    result = mail.read_mail_badge(_lobby(12), mail.load_rules())
    assert result.value == 12
    assert result.profile == ocr.PROFILE_MAIL_BADGE


def test_mail_lives_skips_below_minimum(monkeypatch):
    result, taps, _events = _run_with_frames(monkeypatch, [_lobby(1)], settings={"min_count": 5})
    assert result.status == runtime.AutomationStatus.SUCCESS
    assert result.details["reason"] == "below_minimum"
    assert result.counts["badge"] == 1
    assert taps == []


def test_mail_lives_skips_unreadable_badge(monkeypatch):
    result, taps, _events = _run_with_frames(monkeypatch, [_lobby(None)], settings={"min_count": 1})
    assert result.status == runtime.AutomationStatus.SUCCESS
    assert result.details["skipped"] is True
    assert result.details["reason"] in ("no_digits", "low_confidence")
    assert taps == []


def test_mail_lives_open_failure_reports_target_missing(monkeypatch):
    result, taps, _events = _run_with_frames(monkeypatch, [_lobby(7), _frame(), _lobby(7)])
    assert result.status == runtime.AutomationStatus.TARGET_NOT_FOUND
    assert taps[0] == "mailbox"


def test_mail_lives_happy_path_confirms_and_closes(monkeypatch):
    result, taps, events = _run_with_frames(
        monkeypatch,
        [
            _lobby(9),
            _mailbox(),
            _green_popup(793, 458),
            _green_popup(640, 458),
            _mailbox(),
            _lobby(),
        ],
        settings={"min_count": 1},
    )
    assert result.status == runtime.AutomationStatus.SUCCESS
    assert result.counts["badge"] == 9
    assert result.counts["received"] == 1
    assert taps[:5] == ["mailbox", "lives_tab", "quick_receive", "confirm", "done"]
    assert "close" in taps
    assert any(event["step"] == "Mail Lives: confirm" for event in events)


def test_mail_lives_cancel_during_confirm(monkeypatch):
    stop_event = threading.Event()
    taps = []
    frames = [_lobby(6), _mailbox(), _green_popup(793, 458), _lobby()]

    def fake_capture(_serial):
        if frames:
            return frames.pop(0)
        return _lobby()

    def fake_tap(_serial, name, stop_event=None, wait_after=0.0, wait_jitter=0.0):
        taps.append(name)
        if name == "confirm":
            stop_event.set()

    monkeypatch.setattr(mail, "_capture", fake_capture)
    monkeypatch.setattr(mail, "_tap", fake_tap)
    monkeypatch.setattr(mail.runtime, "human_wait", lambda seconds, jitter=0.0, stop_event=None, rng=None: not runtime.is_cancelled(stop_event))

    result = mail.run_mail_lives("serial-a", stop_event=stop_event, settings={"min_count": 1})
    assert result.status == runtime.AutomationStatus.CANCELLED
    assert "confirm" in taps


def test_parallel_mail_lives_collects_success_and_error(monkeypatch):
    def fake_run(serial, stop_event=None, progress_callback=None, settings=None):
        if serial.endswith("16"):
            return runtime.result(runtime.AutomationStatus.SUCCESS, serial, "ok", {"received": 2, "badge": 5})
        return runtime.result(runtime.AutomationStatus.TARGET_NOT_FOUND, serial, "not found")

    monkeypatch.setattr(mail, "run_mail_lives", fake_run)
    batch = mail.run_parallel_mail_lives(["127.0.0.1:16416", "127.0.0.1:16448"])
    assert len(batch["results"]) == 2
    assert len(batch["errors"]) == 1


if __name__ == "__main__":
    class MonkeyPatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    test_read_mail_badge_from_lobby()
    test_mail_lives_skips_below_minimum(MonkeyPatch())
    test_mail_lives_skips_unreadable_badge(MonkeyPatch())
    test_mail_lives_open_failure_reports_target_missing(MonkeyPatch())
    test_mail_lives_happy_path_confirms_and_closes(MonkeyPatch())
    test_mail_lives_cancel_during_confirm(MonkeyPatch())
    test_parallel_mail_lives_collects_success_and_error(MonkeyPatch())
    print("mail_lives_bot ok")
