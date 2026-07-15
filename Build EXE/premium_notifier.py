"""Non-blocking, structured Discord notifications for Premium AutoFarm."""

from __future__ import annotations

import hashlib
import json
import queue
import threading
import time
import urllib.request
import uuid

import notification_settings


_EVENT_TYPES = {"start", "loop", "stop", "test"}
_STOP_REASONS = {
    "manual": "ผู้ใช้สั่งหยุด",
    "completed": "ทำงานครบตามจำนวนรอบ",
    "error": "บอทหยุดทำงาน",
    "license": "License ใช้งานไม่ได้",
    "app_closed": "ปิดโปรแกรม",
}


def _screen_id(serial: str) -> str:
    return hashlib.sha256(str(serial or "").encode("utf-8")).hexdigest()[:16]


def _number(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sanitize_details(event_type: str, details: dict) -> dict:
    raw = details if isinstance(details, dict) else {}
    if event_type == "start":
        return {"max_loops": max(0, _number(raw.get("max_loops")))}
    if event_type == "loop":
        coins = raw.get("coins")
        return {
            "loops_done": max(0, _number(raw.get("loops_done"))),
            "max_loops": max(0, _number(raw.get("max_loops"))),
            "coins": None if coins is None else max(0, _number(coins)),
            "total": max(0, _number(raw.get("total"))),
        }
    if event_type == "stop":
        reason = str(raw.get("reason") or "error").strip().lower()
        if reason not in _STOP_REASONS:
            reason = "error"
        return {
            "reason": reason,
            "loops_done": max(0, _number(raw.get("loops_done"))),
            "total": max(0, _number(raw.get("total"))),
        }
    return {}


def build_discord_payload(event: dict) -> dict:
    event_type = str(event.get("event_type") or "test")
    screen = str(event.get("screen_label") or "Premium")[:80]
    details = event.get("details") if isinstance(event.get("details"), dict) else {}
    if event_type == "start":
        title = "🟢 เริ่ม AutoFarm"
        maximum = _number(details.get("max_loops"))
        description = "เริ่มทำงานแบบวนไม่จำกัด" if maximum <= 0 else f"เริ่มทำงาน {maximum:,} รอบ"
        color = 0x7ED957
    elif event_type == "loop":
        title = "🍪 AutoFarm จบรอบ"
        loop = _number(details.get("loops_done"))
        maximum = _number(details.get("max_loops"))
        loop_text = f"รอบ {loop:,}" + (f" / {maximum:,}" if maximum > 0 else "")
        coins = details.get("coins")
        coin_text = "อ่านเหรียญไม่ได้" if coins is None else f"{_number(coins):,}"
        description = f"{loop_text}\nCoin รอบนี้: {coin_text}\nCoin รวม: {_number(details.get('total')):,}"
        color = 0xFFD23F
    elif event_type == "stop":
        title = "🔴 AutoFarm หยุดทำงาน"
        description = _STOP_REASONS.get(str(details.get("reason") or ""), "บอทหยุดทำงาน")
        loops = _number(details.get("loops_done"))
        if loops:
            description += f"\nทำสำเร็จทั้งหมด {loops:,} รอบ"
        description += f"\nCoin รวม: {_number(details.get('total')):,}"
        color = 0xFF6B6B
    else:
        title = "🔔 ทดสอบการแจ้งเตือน"
        description = "เชื่อมต่อ Discord สำเร็จ"
        color = 0x6EC6FF
    return {
        "username": "JL Bot Cookie",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,
                "fields": [{"name": "เครื่อง", "value": screen, "inline": True}],
                "footer": {"text": "JL Bot Cookie Premium"},
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(event.get("occurred_at") or time.time())),
            }
        ],
    }


class PremiumNotifier:
    def __init__(self, settings=None):
        self._settings = notification_settings.normalize_settings(settings)
        self._settings_lock = threading.RLock()
        self._queue = queue.Queue(maxsize=100)
        self._thread = None
        self._thread_lock = threading.Lock()
        self._closed = False

    def configure(self, settings) -> None:
        with self._settings_lock:
            self._settings = notification_settings.normalize_settings(settings)

    def settings(self) -> dict:
        with self._settings_lock:
            return dict(self._settings)

    def emit(
        self,
        event_type: str,
        *,
        screen_label: str,
        serial: str = "",
        callback=None,
        **details,
    ) -> bool:
        settings = self.settings()
        event_type = str(event_type or "").strip().lower()
        if event_type not in _EVENT_TYPES:
            return False
        if settings["mode"] == notification_settings.MODE_OFF:
            return False
        if event_type == "start" and not settings["notify_start"]:
            return False
        if event_type == "loop":
            if not settings["notify_loop"]:
                return False
            loops_done = max(0, _number(details.get("loops_done")))
            if not loops_done or loops_done % settings["every_n_loops"]:
                return False
        if event_type == "stop" and not settings["notify_stop"]:
            return False
        event = {
            "event_id": uuid.uuid4().hex,
            "event_type": event_type or "test",
            "occurred_at": int(time.time()),
            "screen_label": str(screen_label or "Premium")[:80],
            "screen_id": _screen_id(serial),
            "details": _sanitize_details(event_type, details),
            "mode": settings["mode"],
            "webhook_url": settings["webhook_url"],
        }
        return self._enqueue(event, callback)

    def test(self, *, screen_label="Premium", serial="test", callback=None) -> bool:
        return self.emit(
            "test",
            screen_label=screen_label,
            serial=serial,
            callback=callback,
        )

    def _enqueue(self, event, callback=None) -> bool:
        if self._closed:
            return False
        self._ensure_thread()
        try:
            self._queue.put_nowait((event, callback))
            return True
        except queue.Full:
            return False

    def _ensure_thread(self) -> None:
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name="premium-discord-notifier", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            event, callback = item
            try:
                ok, message = self._deliver(event)
            except Exception:
                ok, message = False, "ส่งการแจ้งเตือนไม่สำเร็จ"
            if callback:
                try:
                    callback(ok, message)
                except Exception:
                    pass
            self._queue.task_done()

    def _deliver(self, event) -> tuple[bool, str]:
        if event["mode"] == notification_settings.MODE_CUSTOM:
            return self._post_custom(event)
        return False, "ปิดการแจ้งเตือนอยู่"

    def _post_custom(self, event) -> tuple[bool, str]:
        url = notification_settings.validate_webhook_url(event.get("webhook_url"))
        payload = build_discord_payload(event)
        status, _ = self._post_json(url, payload)
        if status in {200, 204}:
            return True, "ส่งข้อความทดสอบสำเร็จ"
        return False, f"Discord ตอบกลับ HTTP {status}"

    @staticmethod
    def _post_json(url: str, payload: dict) -> tuple[int, dict]:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "JLmain-Premium/1"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read()
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                body = {}
            return int(getattr(response, "status", 200)), body

    def close(self, timeout=0.4) -> None:
        self._closed = True
        thread = self._thread
        if thread is None:
            return
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            return
        thread.join(max(0.0, float(timeout or 0)))
