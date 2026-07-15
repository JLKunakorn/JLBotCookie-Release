from __future__ import annotations

from dataclasses import dataclass, field
import random
import time
from typing import Any, Callable, Dict, Iterable, Optional, Tuple


class AutomationStatus:
    SUCCESS = "success"
    CANCELLED = "cancelled"
    NOT_READY = "not_ready"
    TARGET_NOT_FOUND = "target_not_found"
    TIMEOUT = "timeout"
    ADB_ERROR = "adb_error"


@dataclass
class AutomationResult:
    serial: str
    status: str
    message: str = ""
    counts: Dict[str, int] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == AutomationStatus.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "serial": self.serial,
            "message": self.message,
            "counts": dict(self.counts),
            "details": dict(self.details),
        }


DEFAULT_AUTOFARM_SETTINGS = {
    "enabled": False,
    "max_loops": 0,
    "use_jump": True,
    "use_relay": True,
    "use_faststart": False,
    "use_multibuy": True,
    "boost_potion": True,
    "boost_stopwatch": True,
    "boost_star": True,
    "avoid_revive": True,
    "prevent_inactive": False,
    "human_long_pause": True,
    "use_mail_lives": False,
    "use_relic": True,
    "mail_lives": {"min_count": 5},
    "relic": {},
    "captcha": {},
}

DEFAULT_CLAIM_ITEMS_SETTINGS = {
    "gift_draw": {"enabled": False},
    "relic_claim": {"enabled": False},
    "mail_lives": {"enabled": False, "min_count": 5},
    "friends_hearts": {"enabled": False},
    "treasure_extract": {"enabled": False, "powder_max": 30},
}

_RANDOM = random.SystemRandom()


def ensure_namespaced_settings(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    settings = dict(data or {})
    autofarm = dict(DEFAULT_AUTOFARM_SETTINGS)
    existing_autofarm = settings.get("autofarm")
    if isinstance(existing_autofarm, dict):
        for key, value in existing_autofarm.items():
            if isinstance(value, dict) and isinstance(autofarm.get(key), dict):
                merged = dict(autofarm[key])
                merged.update(value)
                autofarm[key] = merged
            else:
                autofarm[key] = value
    settings["autofarm"] = autofarm
    claim_items = dict(DEFAULT_CLAIM_ITEMS_SETTINGS)
    existing_claim = settings.get("claim_items")
    if isinstance(existing_claim, dict):
        for key, value in existing_claim.items():
            if isinstance(value, dict) and isinstance(claim_items.get(key), dict):
                merged = dict(claim_items[key])
                merged.update(value)
                claim_items[key] = merged
            else:
                claim_items[key] = value
    settings["claim_items"] = claim_items
    return settings


def result(status: str, serial: str, message: str = "", counts: Optional[Dict[str, int]] = None,
           details: Optional[Dict[str, Any]] = None) -> AutomationResult:
    return AutomationResult(
        serial=serial,
        status=status,
        message=message,
        counts=dict(counts or {}),
        details=dict(details or {}),
    )


def is_cancelled(stop_event: Any = None) -> bool:
    return bool(stop_event is not None and hasattr(stop_event, "is_set") and stop_event.is_set())


def emit_progress(progress_callback: Optional[Callable[..., Any]], serial: str, step: str,
                  retry: Optional[int] = None, error: Optional[str] = None) -> None:
    if progress_callback is None:
        return
    payload = {"serial": serial, "step": step, "retry": retry, "error": error}
    try:
        progress_callback(payload)
    except TypeError:
        progress_callback(serial=serial, step=step, retry=retry, error=error)


def human_wait(seconds: float, jitter: float = 0.0, stop_event: Any = None,
               rng: random.Random = _RANDOM) -> bool:
    delay = max(0.0, float(seconds))
    if jitter:
        delay = max(0.0, delay + rng.uniform(-abs(float(jitter)), abs(float(jitter))))
    deadline = time.time() + delay
    while True:
        if is_cancelled(stop_event):
            return False
        remaining = deadline - time.time()
        if remaining <= 0:
            return True
        if stop_event is not None and hasattr(stop_event, "wait"):
            if stop_event.wait(min(0.1, remaining)):
                return False
        else:
            time.sleep(min(0.1, remaining))


def random_between(left: float, right: float, rng: random.Random = _RANDOM) -> float:
    return rng.uniform(float(left), float(right))


def choose_point_in_region(region: Tuple[int, int, int, int],
                           rng: random.Random = _RANDOM) -> Tuple[int, int]:
    x, y, w, h = region
    if w <= 0 or h <= 0:
        raise ValueError("tap region must have positive width and height")
    return (
        rng.randint(int(x), int(x + w - 1)),
        rng.randint(int(y), int(y + h - 1)),
    )


def human_tap_region(serial: str, tap_region: Tuple[int, int, int, int], stop_event: Any = None,
                     wait_after: float = 0.0, wait_jitter: float = 0.0,
                     tapper: Optional[Callable[[str, int, int], Any]] = None,
                     rng: random.Random = _RANDOM) -> Optional[Tuple[int, int]]:
    if is_cancelled(stop_event):
        return None
    px, py = choose_point_in_region(tap_region, rng=rng)
    if tapper is None:
        import adb_core
        tapper = adb_core.adb_tap
    tapper(serial, px, py)
    if wait_after and not human_wait(wait_after, wait_jitter, stop_event, rng=rng):
        return None
    return px, py


def run_mock_worker(serial: str, stop_event: Any = None, progress_callback: Optional[Callable[..., Any]] = None,
                    steps: Optional[Iterable[str]] = None, delay: float = 0.0) -> AutomationResult:
    steps = list(steps or ("queued", "running", "done"))
    for step in steps:
        if is_cancelled(stop_event):
            emit_progress(progress_callback, serial, "cancelled")
            return result(AutomationStatus.CANCELLED, serial, "cancelled")
        emit_progress(progress_callback, serial, step)
        if delay and not human_wait(delay, 0.0, stop_event):
            emit_progress(progress_callback, serial, "cancelled")
            return result(AutomationStatus.CANCELLED, serial, "cancelled")
    return result(AutomationStatus.SUCCESS, serial, "mock worker complete")
