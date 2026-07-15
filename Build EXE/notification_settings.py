"""Secure local settings for Premium Discord notifications."""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit


APP_NAME = "JLmain"
STORE_NAME = "notification_settings.dat"
MODE_OFF = "off"
MODE_CUSTOM = "custom"
MODES = {MODE_OFF, MODE_CUSTOM}

DEFAULT_SETTINGS = {
    "version": 1,
    "mode": MODE_OFF,
    "webhook_url": "",
    "every_n_loops": 1,
    "notify_start": True,
    "notify_loop": True,
    "notify_stop": True,
}

_DPAPI_HEADER = b"JLNS1\0"
_PORTABLE_HEADER = b"JLNS0\0"
_ENTROPY = b"JLmain-Premium-Notification-Settings-v1"
_DISCORD_HOSTS = {
    "discord.com",
    "www.discord.com",
    "canary.discord.com",
    "ptb.discord.com",
    "discordapp.com",
}
_WEBHOOK_PATH = re.compile(r"^/api(?:/v\d+)?/webhooks/\d+/[A-Za-z0-9._-]+/?$")


def _appdata_dir() -> Path:
    root = os.environ.get("APPDATA") or str(Path.home())
    path = Path(root) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _store_path() -> Path:
    return _appdata_dir() / STORE_NAME


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _protect(data: bytes) -> bytes:
    if os.name != "nt":
        return _PORTABLE_HEADER + base64.b64encode(data)
    in_blob, in_buffer = _blob(data)
    entropy_blob, entropy_buffer = _blob(_ENTROPY)
    out_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "JLmain Premium notification settings",
        ctypes.byref(entropy_blob),
        None,
        None,
        0x1,
        ctypes.byref(out_blob),
    )
    _ = (in_buffer, entropy_buffer)
    if not ok:
        raise OSError("Windows DPAPI could not encrypt notification settings")
    try:
        encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    return _DPAPI_HEADER + encrypted


def _unprotect(data: bytes) -> bytes:
    if data.startswith(_PORTABLE_HEADER):
        return base64.b64decode(data[len(_PORTABLE_HEADER):])
    if not data.startswith(_DPAPI_HEADER) or os.name != "nt":
        raise ValueError("notification settings format is not supported")
    encrypted = data[len(_DPAPI_HEADER):]
    in_blob, in_buffer = _blob(encrypted)
    entropy_blob, entropy_buffer = _blob(_ENTROPY)
    out_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        0x1,
        ctypes.byref(out_blob),
    )
    _ = (in_buffer, entropy_buffer)
    if not ok:
        raise OSError("Windows DPAPI could not decrypt notification settings")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def validate_webhook_url(value: str) -> str:
    url = str(value or "").strip()
    if not url:
        raise ValueError("กรุณาใส่ Discord Webhook URL")
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or (parsed.hostname or "").lower() not in _DISCORD_HOSTS:
        raise ValueError("รองรับเฉพาะ Discord Webhook URL แบบ https เท่านั้น")
    if parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
        raise ValueError("Discord Webhook URL ไม่ถูกต้อง")
    if not _WEBHOOK_PATH.fullmatch(parsed.path or ""):
        raise ValueError("Discord Webhook URL ไม่ถูกต้อง")
    return url


def normalize_settings(value=None) -> dict:
    raw = value if isinstance(value, dict) else {}
    result = dict(DEFAULT_SETTINGS)
    mode = str(raw.get("mode") or MODE_OFF).strip().lower()
    result["mode"] = mode if mode in MODES else MODE_OFF
    result["webhook_url"] = str(raw.get("webhook_url") or "").strip()
    try:
        every = int(raw.get("every_n_loops") or 1)
    except (TypeError, ValueError):
        every = 1
    result["every_n_loops"] = max(1, min(1000, every))
    for key in ("notify_start", "notify_loop", "notify_stop"):
        result[key] = bool(raw.get(key, DEFAULT_SETTINGS[key]))
    return result


def load_settings() -> dict:
    try:
        payload = json.loads(_unprotect(_store_path().read_bytes()).decode("utf-8"))
    except (FileNotFoundError, ValueError, OSError, json.JSONDecodeError):
        return normalize_settings()
    return normalize_settings(payload)


def save_settings(value) -> dict:
    settings = normalize_settings(value)
    if settings["mode"] == MODE_CUSTOM:
        settings["webhook_url"] = validate_webhook_url(settings["webhook_url"])
    payload = json.dumps(settings, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_bytes(_protect(payload))
    os.replace(temp, path)
    return settings
