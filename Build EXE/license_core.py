"""Online license client for JLmain.

This module keeps the old public API used by the original app:
check_license, verify_key, activate, acquire_run_lock, release_run_lock,
and get_hwid.

Development mode is unlocked until a license config is provided. For a
release build, set required=true and fill api_url/public_key_hex in
license_config.json before packaging.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


APP_NAME = "JLmain"
CONFIG_NAME = "license_config.json"
STATE_NAME = "license_state.json"
SCREEN_CACHE_DIR_NAME = "screen_license_cache"

CLIENT_VERSION = ""

DEFAULT_CONFIG = {
    "required": False,
    "api_url": "",
    "public_key_hex": "",
    "request_timeout_seconds": 8,
}

DEV_INFO = {
    "type": "dev",
    "tier": "pro",
    "exp": None,
    "id": "local-dev",
    "name": "local-dev-unlocked",
    "plan": "dev",
}


def _base_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _appdata_dir() -> Path:
    root = os.environ.get("APPDATA") or str(Path.home())
    path = Path(root) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _config_paths() -> list[Path]:
    return [_base_dir() / CONFIG_NAME, _appdata_dir() / CONFIG_NAME]


def _state_path() -> Path:
    return _appdata_dir() / STATE_NAME


def _screen_cache_path(key_string: str) -> Path:
    key_hash = hashlib.sha256(str(key_string or "").strip().encode("utf-8")).hexdigest()
    path = _appdata_dir() / SCREEN_CACHE_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{key_hash}.json"


def _read_json(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    bundled_cfg = _read_json(_base_dir() / CONFIG_NAME)
    user_cfg = _read_json(_appdata_dir() / CONFIG_NAME)
    cfg.update(bundled_cfg)
    if bundled_cfg.get("required"):
        # A release build must not be downgraded by a user-writable config file.
        cfg["required"] = True
    else:
        cfg.update(user_cfg)
    cfg["api_url"] = str(cfg.get("api_url") or "").strip()
    cfg["public_key_hex"] = str(cfg.get("public_key_hex") or "").strip()
    cfg["required"] = bool(cfg.get("required", False))
    return cfg


def is_configured() -> bool:
    cfg = _load_config()
    return bool(cfg["api_url"] and cfg["public_key_hex"])


def is_required() -> bool:
    return bool(_load_config().get("required", False))


def is_enabled() -> bool:
    cfg = _load_config()
    return bool(cfg.get("required") or (cfg.get("api_url") and cfg.get("public_key_hex")))


def _load_state() -> dict:
    return _read_json(_state_path())


def _save_state(data: dict) -> None:
    data = dict(data)
    data["saved_at"] = int(time.time())
    _write_json(_state_path(), data)


def get_saved_key() -> str:
    return str(_load_state().get("key") or "")


def _machine_guid() -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except Exception:
        return ""


def get_hwid() -> str:
    parts = [
        _machine_guid(),
        socket.gethostname(),
        os.environ.get("COMPUTERNAME", ""),
        str(uuid.getnode()),
    ]
    raw = "|".join(p for p in parts if p).encode("utf-8", "ignore")
    return hashlib.sha256(b"JLmain|" + raw).hexdigest()[:32].upper()


def get_hwid_v2() -> str:
    """HWID เสถียรกว่าเดิม — ตัด uuid.getnode() (MAC address) ออก เพราะไม่เสถียร
    บนเครื่องที่มี virtual network adapter (MuMu/LDPlayer) ใช้แค่ MachineGuid
    ซึ่งผูกกับ Windows ที่ติดตั้งไว้ ไม่ขยับเว้นแต่ลง Windows ใหม่"""
    parts = [_machine_guid(), socket.gethostname(), os.environ.get("COMPUTERNAME", "")]
    raw = "|".join(p for p in parts if p).encode("utf-8", "ignore")
    return hashlib.sha256(b"JLmain-v2|" + raw).hexdigest()[:32].upper()


def _post_json(url: str, body: dict, timeout: int) -> dict:
    data = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": f"{APP_NAME}/1"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _verify_signed_response(resp: dict, cfg: dict) -> dict | None:
    try:
        raw = base64.b64decode(resp["payload_b64"])
        sig = bytes.fromhex(resp["sig"])
        pub = bytes.fromhex(cfg["public_key_hex"])
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        Ed25519PublicKey.from_public_bytes(pub).verify(sig, raw)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def _payload_is_fresh(payload: dict) -> bool:
    now = int(time.time())
    if not payload.get("ok"):
        return False
    if payload.get("hwid") != get_hwid():
        return False
    token_exp = int(payload.get("token_exp") or 0)
    if token_exp and now > token_exp:
        return False
    exp = int(payload.get("exp") or 0)
    if exp and now > exp:
        return False
    return True


def _info_from_payload(payload: dict) -> dict:
    exp = payload.get("exp")
    return {
        "type": "rental" if exp else "online",
        "tier": payload.get("tier") or "",
        "exp": exp,
        "id": payload.get("id") or payload.get("code") or "online",
        "name": payload.get("name") or payload.get("plan") or "online-license",
        "plan": payload.get("plan") or "",
        "key_tier": payload.get("key_tier") or payload.get("product_tier") or "premium",
        "token_exp": payload.get("token_exp"),
        "app_version": payload.get("app_version") or "",
        "download_url": payload.get("download_url") or "",
    }


def _cached_result(cfg: dict) -> tuple[bool, dict | str]:
    state = _load_state()
    resp = state.get("server_response")
    if not isinstance(resp, dict):
        return False, "ยังไม่มี token ที่แคชไว้"
    payload = _verify_signed_response(resp, cfg)
    if not payload or not _payload_is_fresh(payload):
        return False, "token หมดอายุหรือไม่ถูกต้อง"
    return True, _info_from_payload(payload)


def _cached_screen_result(cfg: dict, key_string: str) -> tuple[bool, dict | str]:
    key = str(key_string or "").strip()
    state = _read_json(_screen_cache_path(key))
    expected_id = hashlib.sha256(key.encode("utf-8")).hexdigest()
    if state.get("key_id") != expected_id:
        return False, "screen license cache does not match this key"
    resp = state.get("server_response")
    if not isinstance(resp, dict):
        return False, "no cached token for this screen license"
    payload = _verify_signed_response(resp, cfg)
    if not payload or not _payload_is_fresh(payload):
        return False, "screen license token is expired or invalid"
    return True, _info_from_payload(payload)


def verify_key(key_string=None):
    cfg = _load_config()
    if not is_enabled():
        return True, dict(DEV_INFO)
    if not is_configured():
        return False, "ยังไม่ได้ตั้งค่า license server/public key"

    key = str(key_string or "").strip()
    if not key:
        return False, "กรุณาใส่ license key"

    try:
        resp = _post_json(
            cfg["api_url"],
            {
                "key": key,
                "hwid": get_hwid(),
                "hwid_v2": get_hwid_v2(),
                "app": APP_NAME,
                "client_version": CLIENT_VERSION,
            },
            int(cfg.get("request_timeout_seconds") or 8),
        )
        payload = _verify_signed_response(resp, cfg)
        if not payload:
            return False, "server response signature ไม่ถูกต้อง"
        if payload.get("hwid") != get_hwid():
            return False, "HWID ใน token ไม่ตรงกับเครื่องนี้"
        if not payload.get("ok"):
            return False, str(payload.get("msg") or "license ไม่ผ่าน")
        _save_state({"key": key, "hwid": get_hwid(), "server_response": resp, "payload": payload})
        return True, _info_from_payload(payload)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        ok, info = _cached_result(cfg)
        if ok:
            return ok, info
        return False, f"ติดต่อ license server ไม่ได้: {exc}"
    except Exception as exc:
        return False, f"ตรวจ license ไม่สำเร็จ: {exc}"


def verify_screen_key(key_string=None):
    """Verify an extra screen key without replacing the primary key state."""
    cfg = _load_config()
    if not is_enabled():
        return True, dict(DEV_INFO)
    if not is_configured():
        return False, "license server/public key is not configured"

    key = str(key_string or "").strip()
    if not key:
        return False, "please enter a license key"

    try:
        resp = _post_json(
            cfg["api_url"],
            {
                "key": key,
                "hwid": get_hwid(),
                "hwid_v2": get_hwid_v2(),
                "app": APP_NAME,
                "client_version": CLIENT_VERSION,
            },
            int(cfg.get("request_timeout_seconds") or 8),
        )
        payload = _verify_signed_response(resp, cfg)
        if not payload:
            return False, "license server response signature is invalid"
        if payload.get("hwid") != get_hwid():
            return False, "license HWID does not match this computer"
        if not payload.get("ok"):
            return False, str(payload.get("msg") or "license rejected")
        _write_json(
            _screen_cache_path(key),
            {
                "key_id": hashlib.sha256(key.encode("utf-8")).hexdigest(),
                "hwid": get_hwid(),
                "server_response": resp,
                "payload": payload,
                "saved_at": int(time.time()),
            },
        )
        return True, _info_from_payload(payload)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        ok, info = _cached_screen_result(cfg, key)
        if ok:
            return ok, info
        if key == get_saved_key():
            ok, info = _cached_result(cfg)
            if ok:
                return ok, info
        return False, f"could not contact license server: {exc}"
    except Exception as exc:
        return False, f"screen license verification failed: {exc}"


def check_screen_key(key_string=None, force_online=False):
    """Check one assigned screen key using its own cache and heartbeat."""
    cfg = _load_config()
    if not is_enabled():
        return True, dict(DEV_INFO)
    if not is_configured():
        return False, "license server/public key is not configured"
    key = str(key_string or "").strip()
    if not key:
        return False, "please enter a license key"
    if not force_online:
        ok, info = _cached_screen_result(cfg, key)
        if ok:
            return ok, info
        if key == get_saved_key():
            ok, info = _cached_result(cfg)
            if ok:
                return ok, info
    return verify_screen_key(key)


def activate(key_string=None):
    return verify_key(key_string)


def check_license(force_online=False):
    cfg = _load_config()
    if not is_enabled():
        return True, dict(DEV_INFO)
    if not is_configured():
        return False, "ยังไม่ได้ตั้งค่า license server/public key"

    key = get_saved_key()
    if not key:
        return False, "ยังไม่มี license key"

    if not force_online:
        ok, info = _cached_result(cfg)
        if ok:
            return ok, info
    return verify_key(key)


def acquire_run_lock():
    ok, _ = check_license(force_online=True)
    return bool(ok)


def release_run_lock():
    return None
