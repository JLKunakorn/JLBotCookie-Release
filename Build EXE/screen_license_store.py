"""Encrypted storage for additional Premium screen license keys.

The primary application key remains in license_core/license_state.json. This
module stores only the extra keys that unlock concurrent AutoFarm screens.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import time


APP_NAME = "JLmain"
STORE_NAME = "screen_keys.dat"
_DPAPI_HEADER = b"JLKS1\0"
_PORTABLE_HEADER = b"JLKS0\0"
_ENTROPY = b"JLmain-Premium-Screen-License-v1"


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
        "JLmain Premium screen keys",
        ctypes.byref(entropy_blob),
        None,
        None,
        0x1,
        ctypes.byref(out_blob),
    )
    _ = (in_buffer, entropy_buffer)
    if not ok:
        raise OSError("Windows DPAPI could not encrypt screen keys")
    try:
        encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    return _DPAPI_HEADER + encrypted


def _unprotect(data: bytes) -> bytes:
    if data.startswith(_PORTABLE_HEADER):
        return base64.b64decode(data[len(_PORTABLE_HEADER):])
    if not data.startswith(_DPAPI_HEADER) or os.name != "nt":
        raise ValueError("screen key store format is not supported")
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
        raise OSError("Windows DPAPI could not decrypt screen keys")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def key_id(key: str) -> str:
    normalized = str(key or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def mask_key(key: str) -> str:
    value = str(key or "").strip()
    if len(value) <= 8:
        return "*" * max(4, len(value))
    return f"{value[:4]}****{value[-4:]}"


def load_keys() -> list[dict]:
    path = _store_path()
    try:
        raw = _unprotect(path.read_bytes())
        payload = json.loads(raw.decode("utf-8"))
    except FileNotFoundError:
        return []
    except Exception:
        return []
    items = payload.get("keys") if isinstance(payload, dict) else []
    result = []
    seen = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        item_id = key_id(key)
        if not key or item_id in seen:
            continue
        seen.add(item_id)
        result.append(
            {
                "id": item_id,
                "key": key,
                "added_at": int(item.get("added_at") or 0),
            }
        )
    return result


def save_keys(items: list[dict]) -> None:
    clean = []
    seen = set()
    for item in items or []:
        key = str((item or {}).get("key") or "").strip()
        item_id = key_id(key)
        if not key or item_id in seen:
            continue
        seen.add(item_id)
        clean.append(
            {
                "id": item_id,
                "key": key,
                "added_at": int((item or {}).get("added_at") or time.time()),
            }
        )
    payload = json.dumps(
        {"version": 1, "keys": clean},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_bytes(_protect(payload))
    os.replace(temp, path)


def add_key(key: str, primary_key: str = "") -> dict:
    value = str(key or "").strip()
    if not value:
        raise ValueError("Please enter a license key for the additional screen")
    item_id = key_id(value)
    if primary_key and item_id == key_id(primary_key):
        raise ValueError("This is already the primary license key")
    items = load_keys()
    if any(item["id"] == item_id for item in items):
        raise ValueError("This additional license key has already been added")
    item = {"id": item_id, "key": value, "added_at": int(time.time())}
    items.append(item)
    save_keys(items)
    return item


def remove_key(item_id: str) -> bool:
    target = str(item_id or "").strip()
    items = load_keys()
    kept = [item for item in items if item["id"] != target]
    if len(kept) == len(items):
        return False
    save_keys(kept)
    return True
