import os
import sys
import threading

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import premium_runtime as runtime
from ClaimItems.RelicClaim import relic_claim_bot as relic


def _frame():
    return np.full((720, 1280, 3), 255, dtype=np.uint8)


def _paste_template(frame, name, x, y):
    tpl = cv2.imread(os.path.join(relic.TEMPLATE_DIR, name), cv2.IMREAD_COLOR)
    h, w = tpl.shape[:2]
    frame[y:y + h, x:x + w] = tpl
    return frame


def _lobby():
    return _paste_template(_frame(), "lobby_play.png", 950, 630)


def _indicator():
    frame = _lobby()
    return _paste_template(frame, "relic_get.png", 498, 68)


def _title():
    return _paste_template(_frame(), "relic_title.png", 520, 130)


def _green_button(x=640, y=576):
    frame = _title()
    frame[y - 30:y + 30, x - 30:x + 30] = (20, 220, 20)
    return frame


def _run_with_frames(monkeypatch, frames, stop_event=None):
    taps = []
    events = []

    def fake_capture(_serial):
        if frames:
            return frames.pop(0)
        return _lobby()

    monkeypatch.setattr(relic, "_capture", fake_capture)
    monkeypatch.setattr(relic, "_tap", lambda serial, name, stop_event=None, wait_after=0.0, wait_jitter=0.0: taps.append(name))
    monkeypatch.setattr(relic.runtime, "human_wait", lambda seconds, jitter=0.0, stop_event=None, rng=None: not runtime.is_cancelled(stop_event))
    result = relic.run_relic_claim("serial-a", stop_event=stop_event, progress_callback=events.append)
    return result, taps, events


def test_relic_claim_skips_when_indicator_missing(monkeypatch):
    result, taps, _events = _run_with_frames(monkeypatch, [_lobby()])
    assert result.status == runtime.AutomationStatus.SUCCESS
    assert result.details["skipped"] is True
    assert result.details["reason"] == "no_indicator"
    assert result.counts["claimed"] == 0
    assert taps == []


def test_relic_claim_requires_lobby(monkeypatch):
    result, taps, _events = _run_with_frames(monkeypatch, [_frame()])
    assert result.status == runtime.AutomationStatus.NOT_READY
    assert taps == []


def test_relic_claim_open_failure_reports_target_missing(monkeypatch):
    result, taps, _events = _run_with_frames(monkeypatch, [_indicator(), _frame()])
    assert result.status == runtime.AutomationStatus.TARGET_NOT_FOUND
    assert taps == ["open"]


def test_relic_claim_happy_path_claims_and_closes(monkeypatch):
    result, taps, events = _run_with_frames(
        monkeypatch,
        [
            _indicator(),
            _title(),
            _green_button(),
            _green_button(),
            _title(),
            _title(),
            _title(),
            _title(),
            _title(),
            _lobby(),
        ],
    )
    assert result.status == runtime.AutomationStatus.SUCCESS
    assert result.counts["claimed"] == 2
    assert taps == ["open", "claim", "claim", "close"]
    assert any(event["step"] == "Relic Claim: claim reward" for event in events)


def test_relic_claim_cancel_during_claim_loop(monkeypatch):
    stop_event = threading.Event()
    taps = []
    events = []
    frames = [_indicator(), _title(), _green_button(), _lobby()]

    def fake_capture(_serial):
        if frames:
            return frames.pop(0)
        return _lobby()

    def fake_tap(_serial, name, stop_event=None, wait_after=0.0, wait_jitter=0.0):
        taps.append(name)
        if name == "claim":
            stop_event.set()

    monkeypatch.setattr(relic, "_capture", fake_capture)
    monkeypatch.setattr(relic, "_tap", fake_tap)
    monkeypatch.setattr(relic.runtime, "human_wait", lambda seconds, jitter=0.0, stop_event=None, rng=None: not runtime.is_cancelled(stop_event))

    result = relic.run_relic_claim("serial-a", stop_event=stop_event, progress_callback=events.append)
    assert result.status == runtime.AutomationStatus.CANCELLED
    assert taps == ["open", "claim"]


def test_parallel_relic_claim_collects_success_and_error(monkeypatch):
    def fake_run(serial, stop_event=None, progress_callback=None, settings=None):
        if serial.endswith("16"):
            return runtime.result(runtime.AutomationStatus.SUCCESS, serial, "ok", {"claimed": 2})
        return runtime.result(runtime.AutomationStatus.TARGET_NOT_FOUND, serial, "not found")

    monkeypatch.setattr(relic, "run_relic_claim", fake_run)
    batch = relic.run_parallel_relic_claim(["127.0.0.1:16416", "127.0.0.1:16448"])
    assert len(batch["results"]) == 2
    assert len(batch["errors"]) == 1


if __name__ == "__main__":
    class MonkeyPatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    test_relic_claim_skips_when_indicator_missing(MonkeyPatch())
    test_relic_claim_requires_lobby(MonkeyPatch())
    test_relic_claim_open_failure_reports_target_missing(MonkeyPatch())
    test_relic_claim_happy_path_claims_and_closes(MonkeyPatch())
    test_relic_claim_cancel_during_claim_loop(MonkeyPatch())
    test_parallel_relic_claim_collects_success_and_error(MonkeyPatch())
    print("relic_claim_bot ok")
