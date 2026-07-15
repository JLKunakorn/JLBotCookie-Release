import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time

import cv2
import numpy as np


EXPECTED_W, EXPECTED_H = 1280, 720
MUMU_PORTS = [16384 + i * 32 for i in range(20)]
EXTRA_PORTS = [7555, 5555, 21503]
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
SHOW_DEBUG = os.environ.get("JLBOT_DEBUG", "").strip() == "1"
ROOT = os.path.dirname(os.path.abspath(__file__))
_STRAY_POPUP_RULES = [
    {
        "name": "rule_11_Congratulation",
        "template": "rule_11_Congratulation.png",
        "scan": (381, 109, 531, 67),
        "tap": (635, 567),
        "threshold": 0.85,
    },
    {
        "name": "rule_10_XNews",
        "template": "rule_10_XNews.png",
        "scan": (1103, 55, 48, 36),
        "tap": (1123, 73),
        "threshold": 0.85,
    },
    {
        "name": "rule_13_XNoti",
        "template": "rule_13_XNoti.png",
        "scan": (1111, 39, 26, 28),
        "tap": (1123, 73),
        "threshold": 0.85,
    },
    {
        "name": "rule_12_DailyCheckin",
        "template": "rule_12_DailyCheckin.png",
        "scan": (480, 21, 321, 48),
        "tap": (633, 648),
        "threshold": 0.85,
    },
]
_STRAY_POPUP_TEMPLATE_CACHE = {}
_SCREENCAP_FAILURE_LOGGED = {}
_DEVICE_STOP_EVENTS = {}
_DEVICE_STOP_LOCK = threading.RLock()


def register_device_stop_event(serial, stop_event):
    with _DEVICE_STOP_LOCK:
        _DEVICE_STOP_EVENTS[serial] = stop_event


def unregister_device_stop_event(serial, stop_event=None):
    with _DEVICE_STOP_LOCK:
        current = _DEVICE_STOP_EVENTS.get(serial)
        if stop_event is None or current is stop_event:
            _DEVICE_STOP_EVENTS.pop(serial, None)


def device_stop_event(serial):
    with _DEVICE_STOP_LOCK:
        return _DEVICE_STOP_EVENTS.get(serial)


def is_device_cancelled(serial, stop_event=None):
    event = stop_event or device_stop_event(serial)
    return bool(event is not None and event.is_set())


def interruptible_wait(serial, seconds, stop_event=None):
    event = stop_event or device_stop_event(serial)
    if event is None:
        time.sleep(max(0.0, float(seconds)))
        return True
    return not event.wait(max(0.0, float(seconds)))


def _run_cancellable(cmd, serial, timeout, text=True, errors="ignore"):
    if is_device_cancelled(serial):
        empty = "" if text else b""
        return subprocess.CompletedProcess(cmd, -1, empty, empty)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        errors=errors if text else None,
        creationflags=NO_WINDOW,
    )
    deadline = time.monotonic() + float(timeout)
    while True:
        if is_device_cancelled(serial):
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            return subprocess.CompletedProcess(cmd, -1, stdout, stderr)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            process.kill()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr)
        try:
            stdout, stderr = process.communicate(timeout=min(0.1, remaining))
            return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            continue


def find_adb() -> str:
    bundle_root = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)) if getattr(sys, "frozen", False) else ROOT
    bundled = os.path.join(bundle_root, "adb_bin", "adb.exe")
    if os.path.exists(bundled):
        return bundled

    candidates = [
        r"C:\Program Files\Netease\MuMuPlayer\nx_device\12.0\shell\adb.exe",
        r"C:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe",
        r"C:\Program Files\Netease\MuMu Player 12\shell\adb.exe",
        r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
        r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0\shell\adb.exe",
        r"D:\Program Files\Netease\MuMuPlayer\nx_device\12.0\shell\adb.exe",
        r"D:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe",
        r"D:\LDPlayer\LDPlayer14\adb.exe",
        r"C:\LDPlayer\LDPlayer14\adb.exe",
        r"C:\LDPlayer\LDPlayer9\adb.exe",
        r"C:\LDPlayer\LDPlayer4.0\adb.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    found = shutil.which("adb")
    return found or "adb"


ADB_PATH = find_adb()


def adb_no_serial(args, timeout=10):
    return subprocess.run(
        [ADB_PATH] + args,
        capture_output=True,
        text=True,
        errors="ignore",
        creationflags=NO_WINDOW,
        timeout=timeout,
    )


_adb_no_serial = adb_no_serial


def run_adb(serial, args, timeout=15):
    cmd = [ADB_PATH, "-s", serial] + args
    res = _run_cancellable(cmd, serial, timeout, text=True, errors="ignore")
    return res.returncode, res.stdout, res.stderr


def _port_open(port, host="127.0.0.1", timeout=0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


port_open = _port_open


def adb_connect(port):
    return adb_no_serial(["connect", f"127.0.0.1:{port}"], timeout=4)


def list_online_devices() -> list[str]:
    try:
        res = adb_no_serial(["devices"], timeout=10)
    except Exception as exc:
        log(f"ค้นหารายการเครื่องไม่สำเร็จ — {describe_error(exc)}")
        return []
    devices = []
    for line in res.stdout.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].strip() == "device":
            devices.append(parts[0].strip())
    return devices


def _serial_port(serial):
    try:
        return int(serial.rsplit(":", 1)[1]) if serial.startswith("127.0.0.1:") else -1
    except Exception:
        return -1


def discover_mumu_devices() -> list[str]:
    ports = MUMU_PORTS + EXTRA_PORTS
    for port in ports:
        if _port_open(port):
            try:
                adb_connect(port)
            except Exception:
                pass

    online = list_online_devices()
    by_port = {dev: _serial_port(dev) for dev in online}
    found = []
    for port in ports:
        for dev, dev_port in by_port.items():
            if dev_port == port and dev not in found:
                found.append(dev)
    return found


def select_mumu_device() -> str | None:
    devices = discover_mumu_devices()
    if devices:
        return devices[0]

    log("[WARN] ไม่พบเครื่องเลยในรอบแรก ลอง kill adb server แล้วค้นหาใหม่...", debug=True)
    try:
        adb_no_serial(["kill-server"], timeout=5)
    except Exception as e:
        log(f"  [adb] kill-server error: {e}", debug=True)
    time.sleep(1.0)

    devices = discover_mumu_devices()
    if devices:
        return devices[0]

    online = list_online_devices()
    if online:
        log(f"[WARN] ไม่พบพอร์ต MuMu โดยตรง ใช้ device ออนไลน์ตัวแรกแทน: {online[0]}")
        return online[0]
    log("ไม่พบเครื่อง — เปิด MuMu/LDPlayer เข้าเกมให้เรียบร้อย ตั้งความละเอียด 1280x720 แล้วกดรีเฟรช")
    return None


def adb_tap(serial, x, y):
    """กดแตะจอแบบรวดเร็วโดยใช้ input tap โดยตรง"""
    run_adb(serial, ["shell", "input", "tap", str(int(x)), str(int(y))])


def adb_swipe(serial, x1, y1, x2, y2, dur_ms):
    run_adb(
        serial,
        [
            "shell",
            "input",
            "swipe",
            str(int(x1)),
            str(int(y1)),
            str(int(x2)),
            str(int(y2)),
            str(int(dur_ms)),
        ],
    )


def _load_stray_popup_template(rule):
    name = rule["name"]
    if name not in _STRAY_POPUP_TEMPLATE_CACHE:
        path = os.path.join(ROOT, "templates", rule["template"])
        _STRAY_POPUP_TEMPLATE_CACHE[name] = cv2.imread(path)
    return _STRAY_POPUP_TEMPLATE_CACHE[name]


def _match_stray_popup(img):
    if img is None:
        return None

    for rule in _STRAY_POPUP_RULES:
        template = _load_stray_popup_template(rule)
        if template is None:
            continue

        x, y, w, h = rule["scan"]
        roi = img[y:y + h, x:x + w]
        if roi.size == 0:
            continue
        if template.shape[0] > roi.shape[0] or template.shape[1] > roi.shape[1]:
            continue

        result = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, _ = cv2.minMaxLoc(result)
        if score >= rule["threshold"]:
            return rule
    return None


def _exec_out_screenshot(serial):
    result = _run_cancellable(
        [ADB_PATH, "-s", serial, "exec-out", "screencap", "-p"],
        serial,
        timeout=10,
        text=False,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    img_array = np.frombuffer(result.stdout, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        return None
    return img


_ADB_SERVER = ("127.0.0.1", 5037)
_FB_UNSUPPORTED = set()


def _framebuffer_screenshot(serial, timeout=8):
    """Capture raw pixels through the adb framebuffer service. Return BGR ndarray or None."""
    if serial in _FB_UNSUPPORTED or is_device_cancelled(serial):
        return None
    s = socket.socket()
    try:
        deadline = time.monotonic() + float(timeout)
        s.settimeout(min(0.2, float(timeout)))
        s.connect(_ADB_SERVER)

        def recv_exact(size):
            data = bytearray()
            while len(data) < size:
                if is_device_cancelled(serial) or time.monotonic() >= deadline:
                    return None
                try:
                    chunk = s.recv(size - len(data))
                except socket.timeout:
                    continue
                if not chunk:
                    return None
                data.extend(chunk)
            return bytes(data)

        def send(cmd):
            if is_device_cancelled(serial):
                return False
            s.sendall(("%04x%s" % (len(cmd), cmd)).encode())
            return recv_exact(4) == b"OKAY"

        if not send(f"host:transport:{serial}"):
            return None
        if not send("framebuffer:"):
            return None

        head = recv_exact(4)
        if head is None:
            return None
        version = struct.unpack("<I", head)[0]
        if version != 2:
            _FB_UNSUPPORTED.add(serial)
            return None

        rest = recv_exact(48)
        if rest is None:
            return None
        head += rest
        bpp = struct.unpack("<I", head[4:8])[0]
        size = struct.unpack("<I", head[12:16])[0]
        width, height = struct.unpack("<II", head[16:24])
        if bpp != 32 or size <= 0 or size != width * height * 4 or size > 60_000_000:
            _FB_UNSUPPORTED.add(serial)
            return None

        data = bytearray(size)
        view = memoryview(data)
        received = 0
        while received < size:
            if is_device_cancelled(serial) or time.monotonic() >= deadline:
                return None
            try:
                count = s.recv_into(view[received:], size - received)
            except socket.timeout:
                continue
            if not count:
                return None
            received += count

        arr = np.frombuffer(bytes(data), dtype=np.uint8).reshape(height, width, 4)
        return np.ascontiguousarray(arr[:, :, :3][:, :, ::-1])
    except Exception:
        return None
    finally:
        try:
            s.close()
        except Exception:
            pass


def _capture_raw(serial):
    """Try the fast framebuffer path first, then fall back to the existing PNG path."""
    img = _framebuffer_screenshot(serial)
    if img is not None:
        return img
    return _exec_out_screenshot(serial)


def adb_screencap(serial):
    """Capture the screen through binary adb exec-out and decode it in memory."""
    try:
        if is_device_cancelled(serial):
            return None
        img = _capture_raw(serial)
        if img is None:
            if is_device_cancelled(serial):
                return None
            now = time.monotonic()
            if now - _SCREENCAP_FAILURE_LOGGED.get(serial, 0.0) >= 10.0:
                log(
                    f"ถ่ายภาพเครื่อง {serial} ไม่สำเร็จ — เครื่องอาจปิด/ยังไม่เข้าเกม/ความละเอียดผิด "
                    "ตรวจว่าเครื่องออนไลน์และตั้งเป็น 1280x720 แล้วลองใหม่"
                )
                _SCREENCAP_FAILURE_LOGGED[serial] = now
            return None
        _SCREENCAP_FAILURE_LOGGED.pop(serial, None)
        matched = _match_stray_popup(img)
        if matched:
            tap_x, tap_y = matched["tap"]
            log(f"ปิดป๊อปอัปที่ค้างอยู่ระหว่างทำงาน (auto): {matched['name']}")
            adb_tap(serial, tap_x, tap_y)
            if not interruptible_wait(serial, 0.6):
                return None
            img = _capture_raw(serial)
        return img
    except Exception as exc:
        now = time.monotonic()
        if now - _SCREENCAP_FAILURE_LOGGED.get(serial, 0.0) >= 10.0:
            log(f"ถ่ายภาพเครื่อง {serial} ไม่สำเร็จ — {describe_error(exc)}")
            _SCREENCAP_FAILURE_LOGGED[serial] = now
        return None


def _parse_size(text):
    if not text:
        return None
    value = text.split(":", 1)[-1].strip().split()[0]
    if "x" not in value:
        return None
    w_text, h_text = value.lower().split("x", 1)
    try:
        return int(w_text), int(h_text)
    except ValueError:
        return None


def get_device_resolution(serial) -> tuple[int, int] | None:
    rc, stdout, _ = run_adb(serial, ["shell", "wm", "size"], timeout=8)
    if rc != 0:
        return None

    physical = None
    override = None
    for line in stdout.splitlines():
        if "Override size:" in line:
            override = _parse_size(line)
        elif "Physical size:" in line:
            physical = _parse_size(line)
    return override or physical


def ensure_resolution(serial, enforce=False) -> bool:
    res = get_device_resolution(serial)
    if not res:
        log(f"อ่านความละเอียดเครื่อง {serial} ไม่ได้ — ตรวจว่าเครื่องเปิดอยู่และ ADB เชื่อมต่อแล้ว จากนั้นกดรีเฟรช")
        return False
    w, h = res
    if (w, h) in ((EXPECTED_W, EXPECTED_H), (EXPECTED_H, EXPECTED_W)):
        return True

    log(
        f"ความละเอียดเครื่อง {serial} ไม่ถูกต้อง: ได้ {w}x{h} — "
        "ตั้งเป็น 1280x720 ในโปรแกรมจำลองแล้วเปิดเกมใหม่ มิฉะนั้นพิกัดคลิกจะคลาดเคลื่อน"
    )
    if not enforce:
        return False

    run_adb(serial, ["shell", "wm", "size", f"{EXPECTED_W}x{EXPECTED_H}"], timeout=8)
    res = get_device_resolution(serial)
    if not res:
        return False
    return res in ((EXPECTED_W, EXPECTED_H), (EXPECTED_H, EXPECTED_W))


def describe_error(exc):
    """Return a short customer-facing Thai explanation for common failures."""
    raw = str(exc or "").replace("\r", " ").replace("\n", " ")
    raw = " ".join(raw.split())
    lowered = raw.lower()

    missing_path = str(getattr(exc, "filename", "") or "").lower()
    if "rules.json" in lowered or missing_path.endswith("rules.json"):
        return "ไม่พบ rules.json — ไฟล์ข้อมูลโปรแกรมอาจไม่ครบ ติดตั้ง/แตกไฟล์ใหม่ หรือสร้าง Rule ด้วย ROI Tool"
    if isinstance(exc, FileNotFoundError) and (
        "template" in lowered or "template" in missing_path or missing_path.endswith((".png", ".jpg", ".jpeg"))
    ):
        return "ไม่พบภาพ template — ไฟล์ข้อมูลอาจไม่ครบ ติดตั้ง/แตกไฟล์ใหม่หรือตั้ง ROI ใหม่"
    if isinstance(exc, FileNotFoundError) or "winerror 2" in lowered or "cannot find the file" in lowered:
        return "ไม่พบ adb.exe หรือไฟล์ที่ต้องใช้ — เปิด MuMu/LDPlayer เข้าเกมให้เรียบร้อย แล้วลองใหม่"
    if isinstance(exc, subprocess.TimeoutExpired) or "timed out" in lowered or "timeout" in lowered:
        return "เครื่องตอบสนองช้าหรือไม่ตอบ — เครื่องอาจค้างหรือยังโหลดไม่เสร็จ รอสักครู่แล้วลองใหม่"
    if isinstance(exc, ConnectionRefusedError) or "connection refused" in lowered or "cannot connect" in lowered:
        return "เชื่อมต่อเครื่องจำลองไม่ได้ — ตรวจว่าเปิด MuMu/LDPlayer และเข้าเกมแล้ว"
    if (
        isinstance(exc, PermissionError)
        or "permission denied" in lowered
        or "adbd cannot run as root" in lowered
        or "root access" in lowered
    ):
        return "สิทธิ์ไม่พอ — เปิด Root ในโปรแกรมจำลอง แล้วปิดและเปิดเครื่องจำลองใหม่"
    if isinstance(exc, json.JSONDecodeError):
        return "ไฟล์ตั้งค่าหรือ rules.json เสีย/อ่านไม่ได้ — คืนไฟล์เดิมหรือสร้าง Rule ใหม่ด้วย ROI Tool"
    if isinstance(exc, MemoryError):
        return "หน่วยความจำไม่พอ — ปิดโปรแกรมอื่นหรือลดจำนวนเครื่องที่รันพร้อมกัน"
    if not raw:
        return "ไม่ทราบสาเหตุ — ลองใหม่ และตรวจว่าเครื่องจำลองกับเกมยังเปิดอยู่"
    return raw[:240]


def log(msg, debug=False):
    if debug and not SHOW_DEBUG:
        return
    ts = time.strftime("%H:%M:%S")
    print(f"{ts} {msg}", flush=True)
