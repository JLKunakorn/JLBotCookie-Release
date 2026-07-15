"""
LDPlayer Game Bot - State Machine
=================================
บอทอัตโนมัติสำหรับรันบน Emulator (LDPlayer) ผ่าน ADB + OpenCV
"""
import subprocess
import os
import time
import sys
import random
import threading
import datetime
import json
import socket
import traceback
from enum import Enum, auto
import cv2
import numpy as np
import treasure_extract_roi

import adb_core as side_task_adb
import premium_runtime as side_runtime
from ClaimItems.MailLives import mail_lives_bot
from ClaimItems.RelicClaim import relic_claim_bot

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

LOG_CALLBACK = None
_builtin_print = print

def print(*args, **kwargs):
    try:
        _builtin_print(*args, **kwargs)
    except Exception:
        pass
    if LOG_CALLBACK is not None:
        try:
            LOG_CALLBACK(' '.join((str(a) for a in args)))
        except Exception:
            pass

def resource_path(rel):
    """คืน path ของไฟล์ที่ bundle มากับ .exe (PyInstaller) หรือโฟลเดอร์ของสคริปต์"""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0

def _run(cmd, **kw):
    kw.setdefault('stdin', subprocess.DEVNULL)
    kw.setdefault('stdout', subprocess.DEVNULL)
    kw.setdefault('stderr', subprocess.DEVNULL)
    return subprocess.run(cmd, creationflags=_NO_WINDOW, **kw)

# --- CONFIG & PATHS ---
_DEFAULT_ADB = 'D:\\LDPlayer\\LDPlayer14\\adb.exe'
MULTI_EMU = True

def _emu_adb_paths():
    out = []
    for d in ['C:\\', 'D:\\', 'E:\\']:
        for pf in ['Program Files', 'Program Files (x86)']:
            base = os.path.join(d, pf)
            for mm in ['Netease\\MuMu Player 12', 'Netease\\MuMuPlayer-12.0', 'Netease\\MuMuPlayerGlobal-12.0', 'Netease\\MuMu Player', 'MuMu Player 12', 'MuMuPlayer-12.0', 'MuMuGlobal-12.0']:
                out.append(os.path.join(base, mm, 'shell', 'adb.exe'))
            out.append(os.path.join(base, 'Netease', 'MuMuPlayer', 'nx_device', '12.0', 'shell', 'adb.exe'))
            out.append(os.path.join(base, 'MuMu', 'emulator', 'nemu', 'vmonitor', 'bin', 'adb_server.exe'))
            out.append(os.path.join(base, 'BlueStacks_nxt', 'HD-Adb.exe'))
            out.append(os.path.join(base, 'BlueStacks', 'HD-Adb.exe'))
            out.append(os.path.join(base, 'Nox', 'bin', 'nox_adb.exe'))
            out.append(os.path.join(base, 'Nox', 'bin', 'adb.exe'))
            out.append(os.path.join(base, 'Microvirt', 'MEmu', 'adb.exe'))
    return out

EMU_ADB_PATHS = _emu_adb_paths()
EMU_CONNECT_PORTS = [5555, 5557, 5559, 7555, 16384, 16416, 16448, 16480, 16512, 21503, 62001, 62025, 62026]

def _bundled_adb():
    return resource_path(os.path.join('adb_bundle', 'adb.exe'))

def find_adb():
    cands = [_DEFAULT_ADB]
    roots = ['D:\\LDPlayer', 'C:\\LDPlayer', 'E:\\LDPlayer', 'C:\\Program Files\\LDPlayer', 'C:\\Program Files (x86)\\LDPlayer', 'D:\\Program Files\\LDPlayer', 'C:\\ChangZhi', 'D:\\ChangZhi']
    subs = ['LDPlayer14', 'LDPlayer9', 'LDPlayer64', 'LDPlayer4', '']
    for r in roots:
        for s in subs:
            cands.append(os.path.join(r, s, 'adb.exe'))
    if MULTI_EMU:
        cands += EMU_ADB_PATHS
    for c in cands:
        if os.path.exists(c):
            return c
    b = _bundled_adb()
    if os.path.exists(b):
        return b
    return 'adb'

def find_ld_adb():
    """Return LDPlayer adb.exe when installed, otherwise None."""
    cands = [_DEFAULT_ADB]
    roots = ['D:\\LDPlayer', 'C:\\LDPlayer', 'E:\\LDPlayer', 'C:\\Program Files\\LDPlayer', 'C:\\Program Files (x86)\\LDPlayer', 'D:\\Program Files\\LDPlayer', 'C:\\ChangZhi', 'D:\\ChangZhi']
    subs = ['LDPlayer14', 'LDPlayer9', 'LDPlayer64', 'LDPlayer4', '']
    for r in roots:
        for s in subs:
            cands.append(os.path.join(r, s, 'adb.exe'))
    for c in cands:
        if os.path.exists(c):
            return c
    return None

def find_mumu_adb():
    """Return MuMu adb executable when installed, otherwise None."""
    cands = []
    for d in ['C:\\', 'D:\\', 'E:\\']:
        for pf in ['Program Files', 'Program Files (x86)']:
            base = os.path.join(d, pf)
            for mm in ['Netease\\MuMu Player 12', 'Netease\\MuMuPlayer-12.0', 'Netease\\MuMuPlayerGlobal-12.0', 'Netease\\MuMu Player', 'MuMu Player 12', 'MuMuPlayer-12.0', 'MuMuGlobal-12.0']:
                cands.append(os.path.join(base, mm, 'shell', 'adb.exe'))
            cands.append(os.path.join(base, 'Netease', 'MuMuPlayer', 'nx_device', '12.0', 'shell', 'adb.exe'))
            cands.append(os.path.join(base, 'MuMu', 'emulator', 'nemu', 'vmonitor', 'bin', 'adb_server.exe'))
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def find_ld_console():
    roots = [
        'C:\\LDPlayer', 'D:\\LDPlayer', 'E:\\LDPlayer',
        'C:\\Program Files\\LDPlayer', 'C:\\Program Files (x86)\\LDPlayer',
        'D:\\Program Files\\LDPlayer', 'C:\\ChangZhi', 'D:\\ChangZhi',
    ]
    for root in roots:
        for sub in ['LDPlayer14', 'LDPlayer9', 'LDPlayer64', 'LDPlayer4', '']:
            for exe in ['ldconsole.exe', 'dnconsole.exe']:
                path = os.path.join(root, sub, exe)
                if os.path.exists(path):
                    return path
    return None


def find_mumu_manager():
    candidates = []
    for drive in ['C:\\', 'D:\\', 'E:\\']:
        for folder in ['Program Files', 'Program Files (x86)']:
            base = os.path.join(drive, folder)
            candidates.extend(
                [
                    os.path.join(base, 'Netease', 'MuMuPlayer', 'nx_main', 'MuMuManager.exe'),
                    os.path.join(base, 'Netease', 'MuMu Player 12', 'MuMuManager.exe'),
                    os.path.join(base, 'Netease', 'MuMuPlayer-12.0', 'MuMuManager.exe'),
                ]
            )
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _ld_running_indices():
    """Return authoritative running LDPlayer indexes, or None if unavailable."""
    console = find_ld_console()
    if not console:
        return None
    try:
        result = _run(
            [console, 'list2'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        indexes = []
        for line in (result.stdout or b'').decode(errors='ignore').splitlines():
            fields = [value.strip() for value in line.split(',')]
            if len(fields) < 7:
                continue
            try:
                index = int(fields[0])
                android_started = int(fields[4]) == 1
                player_pid = int(fields[5])
            except (TypeError, ValueError):
                continue
            if android_started and player_pid > 0:
                indexes.append(index)
        return indexes
    except Exception:
        return None


def _mumu_running_ports():
    """Return authoritative running MuMu ADB ports, or None if unavailable."""
    manager = find_mumu_manager()
    if not manager:
        return None
    try:
        result = _run(
            [manager, 'info', '-v', 'all'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        payload = json.loads((result.stdout or b'{}').decode('utf-8', errors='ignore'))
        values = payload.values() if isinstance(payload, dict) else []
        ports = []
        for item in values:
            if not isinstance(item, dict):
                continue
            if not item.get('is_process_started') or not item.get('is_android_started'):
                continue
            try:
                port = int(item.get('adb_port') or 0)
            except (TypeError, ValueError):
                continue
            if port > 0:
                ports.append(port)
        return ports
    except Exception:
        return None

EMU_PROFILES = {
    'LDPlayer': {'find_adb': find_ld_adb, 'ports': [5555 + i * 2 for i in range(20)]},
    'MuMu': {'find_adb': find_mumu_adb, 'ports': [16384 + i * 32 for i in range(20)]},
}

def adb_path_for_emu(emu):
    """Return the adb path for a named emulator profile."""
    profile = EMU_PROFILES.get(emu)
    if profile:
        adb_path = profile['find_adb']()
        if adb_path:
            return adb_path
    b = _bundled_adb()
    if os.path.exists(b):
        return b
    return 'adb'

def _list_online_devices_with_adb(adb_path):
    try:
        r = _run([adb_path, 'devices'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
        devs = []
        for ln in r.stdout.decode(errors='ignore').splitlines()[1:]:
            parts = ln.split('\t')
            if len(parts) == 2 and parts[1].strip() == 'device':
                devs.append(parts[0].strip())
        return devs
    except Exception:
        return []


def _serial_matches_profile(serial, emu):
    """Return True only when a serial belongs to the selected emulator family."""
    value = str(serial or '').strip()
    if not value:
        return False
    port = None
    try:
        if value.startswith('emulator-'):
            port = int(value.rsplit('-', 1)[1])
        elif ':' in value:
            port = int(value.rsplit(':', 1)[1])
    except (TypeError, ValueError):
        return False
    if port is None:
        return False
    if emu == 'MuMu':
        return port in EMU_PROFILES['MuMu']['ports']
    if emu == 'LDPlayer':
        connect_ports = set(EMU_PROFILES['LDPlayer']['ports'])
        local_ports = {5554 + i * 2 for i in range(20)}
        return port in connect_ports or (value.startswith('emulator-') and port in local_ports)
    return True


def _serial_slot_id(serial, emu):
    """Map ADB aliases for one physical emulator to the same slot id."""
    value = str(serial or '').strip()
    try:
        if value.startswith('emulator-'):
            port = int(value.rsplit('-', 1)[1])
            if emu == 'LDPlayer':
                return (emu, max(0, (port - 5554) // 2))
        elif ':' in value:
            port = int(value.rsplit(':', 1)[1])
            if emu == 'LDPlayer':
                return (emu, max(0, (port - 5555) // 2))
            if emu == 'MuMu':
                return (emu, max(0, (port - 16384) // 32))
    except (TypeError, ValueError):
        pass
    return (emu, value)


def _device_has_framebuffer(adb_path, serial, timeout=5):
    """Reject stale ADB entries by requiring a real PNG screencap."""
    try:
        result = _run(
            [adb_path, '-s', str(serial), 'exec-out', 'screencap', '-p'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        data = result.stdout or b''
        return result.returncode == 0 and len(data) > 1024 and data.startswith(b'\x89PNG')
    except Exception:
        return False

def list_emu_instances(emu):
    """Return only matching, online emulator serials with a working framebuffer."""
    profile = EMU_PROFILES.get(emu)
    adb_path = adb_path_for_emu(emu)

    def _try(port):
        try:
            if _port_open(port):
                _run([adb_path, 'connect', '127.0.0.1:%d' % port], timeout=4)
        except Exception:
            return None

    # Prefer each emulator's own manager as the source of truth. ADB servers
    # can share transports, so port 5557 can otherwise be a MuMu alias even
    # when no LDPlayer process is running.
    if emu == 'LDPlayer':
        running_indexes = _ld_running_indices()
        if running_indexes is not None:
            ports = [5555 + index * 2 for index in running_indexes]
            threads = [threading.Thread(target=_try, args=(port,), daemon=True) for port in ports]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
            online = []
            for index, port in zip(running_indexes, ports):
                local_serial = '127.0.0.1:%d' % port
                emulator_serial = 'emulator-%d' % (5554 + index * 2)
                if _device_has_framebuffer(adb_path, emulator_serial):
                    online.append(emulator_serial)
                elif _device_has_framebuffer(adb_path, local_serial):
                    online.append(local_serial)
            return online

    if emu == 'MuMu':
        running_ports = _mumu_running_ports()
        if running_ports is not None:
            threads = [threading.Thread(target=_try, args=(port,), daemon=True) for port in running_ports]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
            return [
                '127.0.0.1:%d' % port
                for port in running_ports
                if _device_has_framebuffer(adb_path, '127.0.0.1:%d' % port)
            ]

    # Compatibility fallback for older emulator versions without a manager
    # command. It still requires a matching port and a valid framebuffer.
    ports = list(profile['ports']) if profile else list(EMU_CONNECT_PORTS)
    threads = [threading.Thread(target=_try, args=(p,), daemon=True) for p in ports]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    candidates = [
        serial for serial in _list_online_devices_with_adb(adb_path)
        if _serial_matches_profile(serial, emu)
    ]
    working = set()
    working_lock = threading.Lock()

    def _probe(serial):
        if _device_has_framebuffer(adb_path, serial):
            with working_lock:
                working.add(serial)

    probes = [threading.Thread(target=_probe, args=(serial,), daemon=True) for serial in candidates]
    for probe in probes:
        probe.start()
    for probe in probes:
        probe.join(timeout=6)
    verified = [serial for serial in candidates if serial in working]
    # LDPlayer commonly exposes one running instance twice (for example,
    # emulator-5556 and 127.0.0.1:5557). Prefer the localhost transport that
    # we explicitly connected and show only one row for that physical slot.
    verified.sort(key=lambda value: (str(value).startswith('emulator-'), candidates.index(value)))
    unique = []
    seen_slots = set()
    for serial in verified:
        slot = _serial_slot_id(serial, emu)
        if slot in seen_slots:
            continue
        seen_slots.add(slot)
        unique.append(serial)
    return unique


def discover_emu_instances(selection=None):
    """Discover LDPlayer and/or MuMu instances with the correct ADB per row."""
    names = ['LDPlayer', 'MuMu'] if selection in (None, '', 'LDPlayer + MuMu') else [selection]
    found = []
    seen = set()
    for emu in names:
        if emu not in EMU_PROFILES:
            continue
        adb_path = adb_path_for_emu(emu)
        for serial in list_emu_instances(emu):
            identity = (emu, serial)
            if identity in seen:
                continue
            seen.add(identity)
            found.append(
                {
                    'emu': emu,
                    'serial': serial,
                    'adb_path': adb_path,
                    'label': _label_for_serial(serial, emu),
                }
            )
    return found

def _label_for_serial(serial, emu='Emulator'):
    """Format adb serials as a friendlier instance name."""
    port = None
    try:
        if serial.startswith('emulator-'):
            port = int(serial.rsplit('-', 1)[1])
        elif ':' in serial:
            port = int(serial.rsplit(':', 1)[1])
    except Exception:
        port = None
    if port is None:
        return '%s - %s' % (emu, serial)
    if emu == 'MuMu' and port >= 16384:
        idx = max(0, (port - 16384) // 32)
    elif port >= 5554:
        base = 5554 if serial.startswith('emulator-') else 5555
        idx = max(0, (port - base) // 2)
    else:
        idx = 0
    return '%s-%d (%d)' % (emu, idx, port)

# --- LICENSE CONTEXTS (JLBOT EXCLUSIVE) ---
_LICENSE_INFO = None
REQUIRED_BOT_TIER = "premium"

def set_license_context(info):
    global _LICENSE_INFO
    _LICENSE_INFO = info

def clear_license_context():
    global _LICENSE_INFO
    _LICENSE_INFO = None

def _require_runtime_license():
    global _LICENSE_INFO
    import license_core
    if not license_core.is_enabled():
        return
    info = _LICENSE_INFO
    if not isinstance(info, dict):
        ok, info = license_core.check_license(force_online=False)
        if not ok:
            clear_license_context()
            raise RuntimeError(f'license ไม่ผ่าน: {info}')
    
    # Check general signature tier validity
    tier = info.get('tier', '').lower() if isinstance(info, dict) else ''
    if tier not in ('pro', 'premium', 'infinite'):
        clear_license_context()
        raise RuntimeError(f'license tier ไม่ถูกต้อง: {tier or "ไม่มี tier"}')
        
    # Check hierarchical bot access (Premium vs Promax)
    key_tier = info.get('key_tier', 'premium').lower()
    if REQUIRED_BOT_TIER == "premium":
        if key_tier not in ("premium", "promax"):
            clear_license_context()
            raise RuntimeError(f'สิทธิ์การใช้งานต่ำเกินไป (ต้องการ Premium ขึ้นไป, คีย์ของคุณคือ {key_tier.upper()})')
    elif REQUIRED_BOT_TIER == "promax":
        if key_tier not in ("promax",):
            clear_license_context()
            raise RuntimeError(f'สิทธิ์การใช้งานไม่เพียงพอ (ต้องการ Promax, คีย์ของคุณคือ {key_tier.upper()})')
            
    set_license_context(info)
    return True

# --- GLOBAL STATES ---
ADB_PATH = find_adb()
ADB_DEVICE = None if MULTI_EMU else 'emulator-5554'
BOT_VERSION = '3.9'
PREVENT_INACTIVE = BOT_VERSION == '2.1'
BOT_TIER = 'pro'

# --- TEMPLATES & THRESHOLDS ---
MATCH_THRESHOLD = 0.85
STABLE_DIFF = 6.0
STABLE_GAP = 0.15
STABLE_MAX_WAIT = 2.2
IMG_TARGET_ITEM = 'templates/target_item.png'
IMG_OK_BUTTON = 'templates/ok_button.png'
IMG_RESULT = 'templates/result_screen.png'
IMG_RELAY = 'templates/relay_prompt.png'
IMG_BOOST_SCREEN = 'templates/boost_screen.png'
IMG_LOBBY_PLAY = 'templates/lobby_play.png'
IMG_FRIEND_POPUP = 'templates/friend_popup.png'
IMG_MODE_POPUP = 'templates/mode_popup.png'
IMG_SENDLIFE_POPUP = 'templates/sendlife_popup.png'
DISMISS_POPUPS = [
    {'name': 'Friend\'s Info', 'img': IMG_FRIEND_POPUP, 'x': (1080, 68), 'th': 0.8},
    {'name': 'Select a Mode', 'img': IMG_MODE_POPUP, 'x': (1240, 90), 'th': 0.8},
    {'name': 'Send Life', 'img': IMG_SENDLIFE_POPUP, 'x': (485, 458), 'th': 0.8}
]
IMG_GENERIC_CLOSE = 'templates/close_x.png'
GENERIC_CLOSE_THRESHOLD = 0.86
GENERIC_CLOSE_FALLBACK = [(1080, 68), (1180, 90)]
IMG_DAILY_CHECKIN = 'templates/dailycheckin_title.png'
CONFIRM_POPUPS = [{'name': 'Daily Check-in', 'img': IMG_DAILY_CHECKIN, 'btn': (641, 654), 'th': 0.8}]

# --- SETTINGS ---
SETTINGS = {
    'use_jump': True,
    'run_mode': 'jump',
    'jump_delay_min': 0.14,
    'jump_delay_max': 0.72,
    'slide_delay_min': 0.14,
    'slide_delay_max': 0.72,
    'use_relay': True, 
    'use_multibuy': True, 
    'boost_potion': True, 
    'boost_stopwatch': True, 
    'boost_star': True, 
    'avoid_revive': True, 
    'use_faststart': False,
    'use_relic': True,
    'use_mail_lives': False,
    'treasure_extract_count': 12,
}

# --- SCREEN & COORDINATES ---
IMG_FASTSTART = 'templates/faststart_prompt.png'
BTN_FASTSTART = (655, 345)
FASTSTART_THRESHOLD = 0.9
FASTSTART_WINDOW = 25.0
IMG_PITLIFT = 'templates/pitlift_popup.png'
PITLIFT_THRESHOLD = 0.8
BTN_PITLIFT_NO = None
IMG_BAKERY_TITLE = 'templates/bakery_title.png'
BAKERY_THRESHOLD = 0.72
BTN_BAKERY_CLOSE = (1089, 171)

# --- FRIEND SEND CONSTANTS ---
BTN_FRIEND_SEND_X = 663
FRIEND_ROWS = [320, 420, 525, 620]
FRIEND_SEND_RED_MIN = 0.025
FRIEND_SEND_GREEN_MIN = 0.2
FRIEND_ARROW_YELLOW_MIN = 0.06
FRIEND_ARROW_DIFF_MIN = 0.06
FRIEND_SELF_HILITE_MIN = 0.2
FRIEND_ARROW_HALF = 16
BTN_FRIEND_CONFIRM = (793, 458)
BTN_FRIEND_CANCEL = (485, 458)
BTN_FRIEND_SENT_OK = (640, 458)
FRIEND_POPUP_GREEN_MIN = 0.45
BTN_FRIEND_INFO_CLOSE = (1091, 72)
FRIEND_SCROLL = (420, 585, 420, 350)
FRIEND_LIST_REGION = (145, 280, 705, 645)
IMG_FRIENDS_HEADER = 'templates/friends_header.png'
SEND_HEARTS_MAX_SCROLLS = 3000

# --- TREASURE EXTRACT CONSTANTS ---
TR_MAX_CYCLES = 2000
TR_POWDER_MAX = 30
TR_POWDER_ROI = (1035, 583, 1150, 620)
TR_DIG_THR = 90
BTN_TR_NORMAL = (288, 527)
BTN_TR_CHEST = (640, 360)
BTN_TR_REVEAL_CONFIRM = (640, 568)
BTN_TR_CABINET = (245, 132)
BTN_TR_EXTRACT_ENTER = (600, 684)
BTN_TR_SORT = (310, 96)
BTN_TR_SORT_TIER = (235, 330)
BTN_TR_TOPLEFT = (207, 190)
BTN_TR_EXTRACT_GO = (940, 674)
BTN_TR_EXTRACT_CONFIRM = (640, 518)
BTN_TR_SUCCESS_CONFIRM = (640, 458)
BTN_TR_EXTRACT_CLOSE = (1139, 105)
BTN_TR_GRID_CLOSE = (1122, 101)
IMG_TR_DRAW_TITLE = 'templates/tr_draw_title.png'
IMG_TR_RECEIVED = 'templates/tr_received.png'
IMG_TR_CABINET_TITLE = 'templates/tr_cabinet_title.png'
IMG_TR_EXTRACT_TITLE = 'templates/tr_extract_title.png'
IMG_TR_EXTRACT_CONFIRM = 'templates/tr_extract_confirm.png'
IMG_TR_EXTRACT_SUCCESS = 'templates/tr_extract_success.png'
IMG_TR_EXPAND_POPUP = 'templates/tr_expand_popup.png'
BTN_TR_EXPAND_CLOSE = (640, 458)
BTN_BOX = (540, 560)
BTN_BUY = (925, 292)
BTN_BUY_CONFIRM = (785, 448)
BTN_PLAY = (955, 615)
BTN_LOBBY_PLAY = (1012, 668)
BTN_POPUP_CONFIRM = (625, 585)
BTN_POPUP_CONFIRM_LOW = (630, 620)
BTN_CLOSE_X = (1080, 68)
BTN_MULTI = (1097, 200)
BTN_MULTI_BUY = (635, 588)
BTN_MULTI_CLOSE = (1043, 82)

# --- MULTI-BOOST OPTIONS ---
MULTI_BOOSTS = [
    {'key': 'double_coins', 'name': 'Double Coins', 'pos': (285, 176), 'default': True},
    {'key': 'score_bonus', 'name': '15% score bonus', 'pos': (685, 176), 'default': False},
    {'key': 'hp_drain', 'name': '-15% HP drain', 'pos': (285, 225), 'default': False},
    {'key': 'revive_80hp', 'name': 'Revive once 80HP', 'pos': (685, 225), 'default': False},
    {'key': 'crush_chance', 'name': '70% Crush Chance', 'pos': (285, 274), 'default': False},
    {'key': 'base_speed', 'name': '+17% base speed', 'pos': (685, 274), 'default': False},
    {'key': 'gold_magic', 'name': 'Gold Coin Magic', 'pos': (285, 324), 'default': False},
    {'key': 'less_collision', 'name': '-30% collision dmg', 'pos': (685, 324), 'default': False},
    {'key': 'hp_potion', 'name': '+20% HP from potion', 'pos': (285, 373), 'default': False},
    {'key': 'magnetic', 'name': 'Magnetic Aura', 'pos': (685, 373), 'default': False},
    {'key': 'pit_lifts', 'name': '2 Pit Lifts', 'pos': (285, 423), 'default': False}
]
MULTIBUY_TIMEOUT = 40.0
IMG_MULTIBUY_STOP = 'templates/multibuy_stop.png'
MULTIBUY_STOP_THRESHOLD = 0.8
MULTI_GREEN_THRESHOLD = 0.09
MULTI_CHECK_HALF = 18

for _b in MULTI_BOOSTS:
    SETTINGS.setdefault('multi_' + _b['key'], _b['default'])

# --- RUNNING PARAMETERS ---
BTN_JUMP = (80, 670)
BTN_SLIDE = (1200, 670)
BTN_RELAY = (644, 335)
JUMP_DELAY_MIN = 0.14
JUMP_DELAY_MAX = 0.72
SLIDE_DELAY_MIN = 0.14
SLIDE_DELAY_MAX = 0.72
JUMP_ZONE = (40, 620, 210, 705)
RELAY_THRESHOLD = 0.7
TAP_JITTER = 7
JUMP_JITTER = 28
SLIDE_HOLD_SEC = 0.35
SLIDE_HOLD_MIN = 0.28
SLIDE_HOLD_MAX = 0.45
HUMAN_JUMP_LONG_PAUSE_CHANCE = 0.06
HUMAN_JUMP_LONG_PAUSE_MIN = 0.45
HUMAN_JUMP_LONG_PAUSE_MAX = 1.3
IDLE_ACTION_MIN = 10.0
IDLE_ACTION_MAX = 15.0
IDLE_SLIDE_CHANCE = 0.16666666666666666
IMG_INGAME = 'templates/ingame.png'
INGAME_THRESHOLD = 0.82
PATTERN_FILE = 'pattern.json'
REPLAY_PATTERN = None
BOOST_ITEMS = [
    {'name': 'Potion', 'key': 'boost_potion', 'tap': (210, 430), 'check_img': 'templates/chk_potion.png', 'check_roi': (240, 455, 320, 515)},
    {'name': 'Stopwatch', 'key': 'boost_stopwatch', 'tap': (365, 430), 'check_img': 'templates/chk_stopwatch.png', 'check_roi': (392, 455, 472, 515)},
    {'name': 'Star x2', 'key': 'boost_star', 'tap': (515, 430), 'check_img': 'templates/chk_star.png', 'check_roi': (545, 455, 625, 515)}
]

# --- LOBBY SIDE TASK CONFIG ---
MAIL_MIN_COUNT = 5

CAPTCHA_COUNT = 0
CAPTCHA_CALLBACK = None
CAPTCHA_CHECK_ENABLED = True
LAST_CAPTCHA_CHECK_TIME = 0.0

# พิกัดการ์ด 6 ใบของหน้าแคปช่า (x, y, w, h) @ 1280x720
CAPTCHA_CARD_SLOTS = [
    (365, 200, 140, 190),  # Card 1
    (565, 200, 140, 190),  # Card 2
    (765, 200, 140, 190),  # Card 3
    (365, 450, 140, 190),  # Card 4
    (565, 450, 140, 190),  # Card 5
    (765, 450, 140, 190),  # Card 6
]
CAPTCHA_MOTION_FRAMES = 6      # จำนวนเฟรมที่จับเพื่อดูการขยับของการ์ด
CAPTCHA_MOTION_INTERVAL = 0.2  # เว้นช่วงระหว่างเฟรม (วินาที)
CAPTCHA_MOTION_CONF = 0.85     # ถ้าใบที่ต่างสุดยังคล้ายเกินค่านี้ = ไม่มั่นใจ -> fallback ภาพนิ่ง
CAPTCHA_MAX_ROUNDS = 20        # safety cap กันลูปนิรันดร์ (เดิม 4) — ปกติหลุดเองเมื่อแคปช่าหาย

# --- GIFT DRAW CONFIGS ---
BTN_GIFT_ICON = (400, 672)
BTN_GIFT_DRAW = (930, 613)
BTN_GIFT_BOX = (640, 345)
BTN_GIFT_SKIP = (640, 360)
BTN_GIFT_AGAIN = (797, 575)
BTN_GIFT_CONFIRM = (479, 573)
BTN_GIFT_PET = (640, 575)
BTN_GIFT_CLOSE = (1123, 113)
IMG_GIFTDRAW_TITLE = 'templates/giftdraw_title.png'
IMG_GIFT_PICK = 'templates/gift_pick.png'
GIFT_DRAW_MAX = 2000

CHECK_THRESHOLD = 0.75
DELAY_AFTER_REROLL = 2.0
DELAY_AFTER_PLAY = 3.0
LOOP_SLEEP = 0.3
RESULT_CHECK_INTERVAL = 0.2
RUN_STATE_TIMEOUT = 600.0
BTN_INACTIVE_CONFIRM = (640, 490)
FREEZE_SECS = 8.0
FREEZE_DIFF = 3.0
STOP_FLAG = threading.Event()

# --- BACKEND FUNCTIONS ---

def watch_emergency_key():
    try:
        import keyboard
    except Exception:
        keyboard = None
    if keyboard is not None:
        keyboard.wait('q')
        print('\n[!] กดปุ่ม \'q\' — กำลังหยุดบอท...')
        STOP_FLAG.set()
        return
    import msvcrt
    while not STOP_FLAG.is_set():
        try:
            if msvcrt.kbhit() and msvcrt.getch().lower() == b'q':
                print('\n[!] กดปุ่ม \'q\' — กำลังหยุดบอท...')
                STOP_FLAG.set()
                return
        except Exception:
            pass
        time.sleep(0.05)

def _adb_base():
    cmd = [ADB_PATH]
    if ADB_DEVICE:
        cmd += ['-s', ADB_DEVICE]
    return cmd

def list_online_devices():
    try:
        r = _run([ADB_PATH, 'devices'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
        devs = []
        for ln in r.stdout.decode(errors='ignore').splitlines()[1:]:
            parts = ln.split('\t')
            if len(parts) == 2 and parts[1].strip() == 'device':
                devs.append(parts[0].strip())
        return devs
    except Exception:
        return []

def _config_adb_ports():
    ports = set()
    progdata = os.environ.get('ProgramData', 'C:\\ProgramData')
    for conf in [os.path.join(progdata, 'BlueStacks_nxt', 'bluestacks.conf'), os.path.join(progdata, 'BlueStacks', 'bluestacks.conf')]:
        try:
            with open(conf, encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if 'adb_port' in line and '=\"' in line:
                        v = line.split('=\"', 1)[1].split('\"', 1)[0].strip()
                        if v.isdigit() and 1024 < int(v) < 65536:
                            ports.add(int(v))
        except Exception:
            pass
    return ports

def _candidate_ports():
    ports = set(EMU_CONNECT_PORTS)
    ports |= _config_adb_ports()
    ports.add(7555)
    for p in range(21503, 21544, 10):
        ports.add(p)
    for n in range(0, 20):
        ports.add(16384 + n * 32)
    for p in range(62001, 62101):
        ports.add(p)
    for p in range(5555, 5686, 2):
        ports.add(p)
    ports.discard(5037)
    return sorted(ports)

def _port_open(port, host='127.0.0.1', timeout=0.35):
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
    except Exception:
        return False
    return True

def _detect_emu_ports():
    found = []
    lock = threading.Lock()
    def chk(p):
        if _port_open(p):
            with lock:
                found.append(p)
    threads = [threading.Thread(target=chk, args=(p,), daemon=True) for p in _candidate_ports()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=1.5)
    return sorted(found)

def auto_connect_emulators():
    if not MULTI_EMU:
        return
    if list_online_devices():
        return
    scanned = _detect_emu_ports()
    conf = _config_adb_ports()
    ports = sorted(set(scanned) | conf | set(EMU_CONNECT_PORTS))
    print('[adb] พอร์ตอีมูฯ ที่เจอ(สแกน): %s | จาก config: %s' % (scanned or 'ไม่เจอ', sorted(conf) or 'ไม่มี'))
    def _try(port):
        try:
            _run([ADB_PATH, 'connect', '127.0.0.1:%d' % port], timeout=4)
        except Exception:
            pass
    threads = [threading.Thread(target=_try, args=(p,), daemon=True) for p in ports]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

_DEVICE_LOCKS = {}

def _canonical_device(dev):
    d = str(dev).strip()
    if d.startswith('emulator-'):
        try:
            return '127.0.0.1:%d' % (int(d.split('-', 1)[1]) + 1)
        except Exception:
            return d
    return d

def _acquire_device_lock(dev):
    if os.name != 'nt':
        return True
    key = _canonical_device(dev)
    if key in _DEVICE_LOCKS:
        return True
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    name = 'cookiegame_dev_' + ''.join((ch if ch.isalnum() else '_' for ch in key))
    handle = k32.CreateMutexW(None, False, name)
    if k32.GetLastError() == 183:
        if handle:
            k32.CloseHandle(handle)
        return False
    _DEVICE_LOCKS[key] = handle
    for k in [k for k in _DEVICE_LOCKS if k != key]:
        try:
            k32.CloseHandle(_DEVICE_LOCKS.pop(k))
        except Exception:
            pass
    return True

def auto_select_device():
    global ADB_DEVICE
    online = list_online_devices()
    if not online:
        return False
    if ADB_DEVICE in online:
        return _acquire_device_lock(ADB_DEVICE) or True
    if ADB_DEVICE:
        return False
    for dev in online:
        if _acquire_device_lock(dev):
            print(f'[adb] เลือก device อัตโนมัติ -> \'{dev}\'')
            ADB_DEVICE = dev
            return True
        else:
            print(f'[adb] ข้าม \'{dev}\' (อีกหน้าต่างใช้จอนี้อยู่)')
    print('[adb] ❌ ทุกจอถูกหน้าต่างอื่นใช้หมดแล้ว — เปิดอีมูฯ เพิ่ม หรือปิดหน้าต่างที่ไม่ใช้')
    return False

_IN_CAPTCHA_SOLVER = False


def _wait_while_captcha(stop_event=None):
    """บล็อกระหว่างที่กำลังแก้แคปช่าอยู่ -> ให้แคปช่าทำก่อนงานอื่นทุก state
       คืน True ถ้าถูกสั่งหยุด (STOP_FLAG หรือ stop_event) เพื่อให้ผู้เรียกออกจากลูป"""
    while _IN_CAPTCHA_SOLVER:
        if STOP_FLAG.is_set() or (stop_event is not None and stop_event.is_set()):
            return True
        time.sleep(0.1)
    return False


def _capt_crop_slot(screen, rect):
    x, y, w, h = rect
    h_scr, w_scr = screen.shape[:2]
    x1 = max(0, min(w_scr - 1, int(x)))
    y1 = max(0, min(h_scr - 1, int(y)))
    x2 = max(0, min(w_scr, int(x + w)))
    y2 = max(0, min(h_scr, int(y + h)))
    return screen[y1:y2, x1:x2]


def _capt_card_similarity(a, b, max_shift=2):
    """ความคล้ายของการ์ด 2 ใบจากภาพนิ่ง (จับ shift เล็กน้อยกันภาพเหลื่อม)"""
    if a.size == 0 or b.size == 0:
        return -1.0
    b_resized = cv2.resize(b, (a.shape[1], a.shape[0]))
    a_gray = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    b_gray = cv2.cvtColor(b_resized, cv2.COLOR_BGR2GRAY)
    if max_shift <= 0:
        result = cv2.matchTemplate(a_gray, b_gray, cv2.TM_CCOEFF_NORMED)
        return float(result[0][0])
    best = -1.0
    h, w = a_gray.shape[:2]
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            ax1 = max(0, dx)
            ay1 = max(0, dy)
            ax2 = min(w, w + dx)
            ay2 = min(h, h + dy)
            bx1 = max(0, -dx)
            by1 = max(0, -dy)
            a_crop = a_gray[ay1:ay2, ax1:ax2]
            b_crop = b_gray[by1:by1 + a_crop.shape[0], bx1:bx1 + a_crop.shape[1]]
            if a_crop.size < 1000 or b_crop.shape != a_crop.shape:
                continue
            result = cv2.matchTemplate(a_crop, b_crop, cv2.TM_CCOEFF_NORMED)
            best = max(best, float(result[0][0]))
    return best


def _capt_motion_signature(card_frames, size=(48, 64)):
    """ลายเซ็นการขยับของการ์ด 1 ใบ = ต่อภาพผลต่างระหว่างเฟรมติดกัน"""
    resized = []
    for frame in card_frames:
        if frame.size == 0:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, size).astype(np.float32) / 255.0
        resized.append(gray)
    if len(resized) < 2:
        return np.array([], dtype=np.float32)
    diffs = [cv2.absdiff(prev, curr) for prev, curr in zip(resized, resized[1:])]
    return np.concatenate([d.reshape(-1) for d in diffs]).astype(np.float32)


def _capt_signature_similarity(a, b):
    if a.size == 0 or b.size == 0:
        return -1.0
    length = min(a.size, b.size)
    a = a[:length]
    b = b[:length]
    a_std = float(np.std(a))
    b_std = float(np.std(b))
    if a_std < 1e-6 or b_std < 1e-6:
        return 1.0 if float(np.mean(np.abs(a - b))) < 1e-6 else 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _capt_find_two_by_motion(sequence):
    """เลือกการ์ด 2 ใบที่ขยับต่างจากพวกมากที่สุด -> คืน (picks, scores)"""
    if not sequence:
        return [], []
    card_count = len(sequence[0])
    signatures = []
    for card_idx in range(card_count):
        card_frames = [fs[card_idx] for fs in sequence if len(fs) > card_idx]
        signatures.append(_capt_motion_signature(card_frames))
    scores = []
    for i, sig in enumerate(signatures):
        others = [_capt_signature_similarity(sig, o) for j, o in enumerate(signatures) if i != j]
        scores.append(float(np.mean(others)) if others else -1.0)
    ranked = sorted(range(len(scores)), key=lambda idx: scores[idx])
    return ranked[:2], scores


def _capt_find_two_static(crops):
    """สำรอง: เลือกการ์ด 2 ใบที่ภาพนิ่งต่างจากพวกมากที่สุด"""
    scores = []
    for i, crop in enumerate(crops):
        others = [_capt_card_similarity(crop, o) for j, o in enumerate(crops) if i != j]
        scores.append(float(np.mean(others)) if others else -1.0)
    ranked = sorted(range(len(scores)), key=lambda idx: scores[idx])
    return ranked[:2], scores


def _capt_tap_slot(rect):
    """กดการ์ดแบบเยื้องจากกลางเล็กน้อยเหมือนนิ้วคนจริง (ไม่หลุดขอบการ์ด)"""
    x, y, w, h = rect
    cx = x + w / 2 + random.gauss(0, min(3.0, w / 8))
    cy = y + h / 2 + random.gauss(0, min(3.0, h / 8))
    cx = max(x + 4, min(x + w - 4, cx))
    cy = max(y + 4, min(y + h - 4, cy))
    adb_tap(cx, cy, jitter=0)


def _capt_capture_sequence(frames, interval):
    """จับหลายเฟรมแล้ว crop การ์ดทั้ง 6 ใบต่อเฟรม -> คืน (last_screen, sequence)"""
    last = None
    sequence = []
    for _ in range(frames):
        s = adb_screencap(check_captcha=False)
        if s is None:
            time.sleep(interval)
            continue
        last = s
        sequence.append([_capt_crop_slot(s, r) for r in CAPTCHA_CARD_SLOTS])
        time.sleep(interval)
    return last, sequence


def _capt_title_score(screen, tpl):
    if screen is None:
        return 0.0
    res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(res)
    return float(score)


def check_and_solve_captcha_on_screen(screen):
    """ตรวจ+แก้แคปช่าด้วย motion detection (ดูการ์ดที่ขยับต่างจากพวก) มี fallback ภาพนิ่ง
       คืน True เมื่อ 'ตรวจพบแคปช่า' (จอถือว่า stale ให้ผู้เรียกแคปใหม่) / False เมื่อไม่พบ"""
    global _IN_CAPTCHA_SOLVER, CAPTCHA_COUNT, CAPTCHA_CALLBACK
    tpl_path = 'templates/captcha_title.png'
    if not os.path.exists(tpl_path):
        return False

    tpl = cv2.imread(tpl_path)
    if tpl is None:
        return False
    if _capt_title_score(screen, tpl) < 0.70:
        return False

    _IN_CAPTCHA_SOLVER = True
    print(f'[ระบบแคปช่า] 🚨 ตรวจพบระบบแคปช่าบนจอ {ADB_DEVICE}! -> เริ่มแก้ไขอัตโนมัติ (motion)...')
    solved = False
    try:
        round_idx = 1
        while round_idx <= CAPTCHA_MAX_ROUNDS:
            if STOP_FLAG.is_set():
                break

            last_screen, sequence = _capt_capture_sequence(CAPTCHA_MOTION_FRAMES, CAPTCHA_MOTION_INTERVAL)
            if not sequence:
                break

            picks, scores = _capt_find_two_by_motion(sequence)
            mode = 'motion'
            # ถ้าใบที่ต่างสุดยังคล้ายพวกเกินเกณฑ์ = ไม่มีการขยับชัด -> เทียบภาพนิ่งแทน
            if len(picks) < 2 or scores[picks[0]] >= CAPTCHA_MOTION_CONF:
                base = last_screen if last_screen is not None else screen
                crops = [_capt_crop_slot(base, r) for r in CAPTCHA_CARD_SLOTS]
                picks, scores = _capt_find_two_static(crops)
                mode = 'static'
            if len(picks) < 2:
                break

            print(f'[ระบบแคปช่า] 🎯 ด่านที่ {round_idx} ({mode}) -> เลือกการ์ดใบที่ {picks[0]+1} และ {picks[1]+1}  '
                  f'scores={[round(s, 3) for s in scores]}')

            for i, idx in enumerate(picks):
                _capt_tap_slot(CAPTCHA_CARD_SLOTS[idx])
                if i < len(picks) - 1:
                    time.sleep(random.uniform(0.95, 1.25))
                else:
                    time.sleep(0.3)

            human_sleep(2.0)

            next_screen = adb_screencap(check_captcha=False)
            if next_screen is None:
                break
            score = _capt_title_score(next_screen, tpl)
            if score < 0.70:
                print(f'[ระบบแคปช่า] ✅ แก้ไขสำเร็จ แคปช่าหายไปแล้ว (คะแนนเหลือ = {score:.4f}, {round_idx} รอบ)')
                solved = True
                CAPTCHA_COUNT += 1
                if CAPTCHA_CALLBACK is not None:
                    try:
                        CAPTCHA_CALLBACK(CAPTCHA_COUNT)
                    except Exception:
                        pass
                break

            round_idx += 1

        if not solved and round_idx > CAPTCHA_MAX_ROUNDS:
            print(f'[ระบบแคปช่า] ⚠️ แก้ครบ {CAPTCHA_MAX_ROUNDS} รอบแล้วยังไม่หาย -> หยุดเพื่อความปลอดภัย')

    except Exception as e:
        print(f'[ระบบแคปช่า] ❌ เกิดข้อผิดพลาดขณะแก้แคปช่า: {e}')
        if not getattr(sys, 'frozen', False):
            print(traceback.format_exc())
    finally:
        _IN_CAPTCHA_SOLVER = False

    return True

def adb_screencap(check_captcha=True):
    global _IN_CAPTCHA_SOLVER, LAST_CAPTCHA_CHECK_TIME
    cmd = _adb_base() + ['exec-out', 'screencap', '-p']
    try:
        result = _run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        if not result.stdout:
            print('[ERR] แคปหน้าจอไม่ได้:', result.stderr.decode(errors='ignore'))
            return None
        img_array = np.frombuffer(result.stdout, dtype=np.uint8)
        screen = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if check_captcha and not _IN_CAPTCHA_SOLVER and screen is not None:
            now = time.time()
            should_check = False
            if CAPTCHA_CHECK_ENABLED:
                should_check = True
            else:
                # เช็คหน่วงเวลาช่วงเล่นเกมจริงทุกๆ 3.5 วินาทีต่อครั้ง
                if now - LAST_CAPTCHA_CHECK_TIME >= 3.5:
                    should_check = True
                    
            if should_check:
                LAST_CAPTCHA_CHECK_TIME = now
                if check_and_solve_captcha_on_screen(screen):
                    return adb_screencap(check_captcha=False)
                
        return screen
    except subprocess.TimeoutExpired:
        print('[ERR] ADB screencap timeout')
        return None
    except Exception as e:
        print(f'[ERR] adb_screencap: {e}')
        return None

def _can_screencap(device):
    """ทดสอบว่า device นี้ 'แคปหน้าจอได้จริง' ไหม — กัน device ที่ต่อหลอกๆ (ขึ้น online
       แต่แคปจอไม่ได้ เช่นพอร์ตจาก config ของ MuMu ที่ไม่ใช่ instance ที่รันจริง)
       -> คืน True เฉพาะเมื่อได้ข้อมูลภาพจริงกลับมา"""
    try:
        r = _run([ADB_PATH, '-s', str(device), 'exec-out', 'screencap', '-p'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8)
        return bool(r.stdout) and len(r.stdout) > 2000
    except Exception:
        return False

def adb_screencap_stable(max_wait=None, gap=None, diff=None):
    """แคปหน้าจอ "จนกว่าภาพจะนิ่ง" แล้วค่อยคืน — กันเครื่องช้า/หน่วงอ่านเฟรมกลางทรานสิชัน/เฟรมขาด
       วิธี: แคป 2 เฟรมห่างกัน gap วิ ถ้าต่างกันน้อยกว่า diff (_frame_signature) = ตกตะกอนแล้ว -> คืนเฟรมนั้น
             ยังไม่นิ่ง = แคปใหม่ไปเรื่อยๆ จนนิ่ง หรือครบ max_wait (คืนเฟรมล่าสุด ไม่ค้าง)
       *** ใช้เฉพาะตอนนำทาง/เมนู — ห้ามใช้ตอนวิ่งจริงที่พื้นหลังเลื่อนตลอด (จะไม่มีวันนิ่ง = รอจนหมดเวลาทุกครั้ง) ***
       คืน None ถ้าแคปไม่ได้เลย (เหมือน adb_screencap)"""
    w = max_wait if max_wait is not None else STABLE_MAX_WAIT
    g = gap if gap is not None else STABLE_GAP
    d = diff if diff is not None else STABLE_DIFF
    prev = adb_screencap()
    if prev is None:
        return None
    start = time.time()
    while time.time() - start < w:
        if STOP_FLAG.is_set():
            return prev
        time.sleep(g)
        cur = adb_screencap()
        if cur is None:
            return prev
        s1 = _frame_signature(prev)
        s2 = _frame_signature(cur)
        if float(np.mean(np.abs(s2 - s1))) < d:
            return cur
        prev = cur
    return prev

def human_sleep(base_seconds):
    """นอนหลับสุ่มช่วงเวลาสั้นๆ +/- 15% - 20% เพื่อเลียนแบบพฤติกรรมมนุษย์และหลบหลีกการตรวจจับ"""
    variation = base_seconds * random.uniform(-0.15, 0.20)
    time.sleep(max(0.05, base_seconds + variation))

def adb_tap(x, y, jitter=None):
    j = TAP_JITTER if jitter is None else jitter
    if j and j > 0:
        x = min(1279, max(0, int(x) + random.randint(-j, j)))
        y = min(719, max(0, int(y) + random.randint(-j, j)))
    # เลียนแบบการแตะของมนุษย์ (Dwell Time) ด้วยการ swipe สั้นๆ ที่พิกัดเดิม หน่วงเวลา 70-140ms
    dwell_time = random.randint(70, 140)
    _run(_adb_base() + ['shell', 'input', 'swipe', str(int(x)), str(int(y)), str(int(x)), str(int(y)), str(dwell_time)])

def adb_hold(x, y, duration_sec):
    ms = int(duration_sec * 1000)
    _run(_adb_base() + ['shell', 'input', 'swipe', str(x), str(y), str(x), str(y), str(ms)])

def adb_swipe(x1, y1, x2, y2, duration_ms=300):
    _run(_adb_base() + ['shell', 'input', 'swipe', str(x1), str(y1), str(x2), str(y2), str(duration_ms)])

def adb_slide(jitter=None):
    j = JUMP_JITTER if jitter is None else jitter
    x, y = BTN_SLIDE
    if j and j > 0:
        x = min(1279, max(0, x + random.randint(-j, j)))
        y = min(719, max(0, y + random.randint(-j, j)))
    # เพิ่มการสุ่มระยะเวลากดปุ่มสไลด์เล็กน้อย
    duration = SLIDE_HOLD_SEC + random.uniform(-0.04, 0.05)
    adb_hold(x, y, duration)

def _jump_point():
    x1, y1, x2, y2 = JUMP_ZONE
    return (random.randint(x1, x2), random.randint(y1, y2))


def configured_run_mode(settings=None):
    values = settings if isinstance(settings, dict) else SETTINGS
    fallback = 'jump' if bool(values.get('use_jump', True)) else 'none'
    mode = str(values.get('run_mode') or fallback).strip().lower()
    return mode if mode in {'jump', 'slide', 'jump_slide', 'none'} else fallback


def action_delay_range(action, settings=None):
    values = settings if isinstance(settings, dict) else SETTINGS
    if action == 'slide':
        default_min, default_max = SLIDE_DELAY_MIN, SLIDE_DELAY_MAX
        min_key, max_key = 'slide_delay_min', 'slide_delay_max'
    else:
        default_min, default_max = JUMP_DELAY_MIN, JUMP_DELAY_MAX
        min_key, max_key = 'jump_delay_min', 'jump_delay_max'
    try:
        minimum = float(values.get(min_key, default_min))
        maximum = float(values.get(max_key, default_max))
    except (TypeError, ValueError):
        minimum, maximum = default_min, default_max
    minimum = min(10.0, max(0.05, minimum))
    maximum = min(10.0, max(0.05, maximum))
    if minimum > maximum:
        minimum, maximum = maximum, minimum
    return minimum, maximum


def perform_run_action(mode):
    action = str(mode or 'jump').lower()
    if action == 'jump_slide':
        action = 'jump' if random.random() < 0.5 else 'slide'
    if action == 'slide':
        adb_slide()
        return 'slide'
    adb_tap(*_jump_point(), jitter=0)
    return 'jump'


def wait_action_delay(stop_event, action, settings=None):
    minimum, maximum = action_delay_range(action, settings)
    deadline = time.monotonic() + random.uniform(minimum, maximum)
    while True:
        if STOP_FLAG.is_set() or stop_event.is_set():
            return False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        stop_event.wait(min(0.05, remaining))

_TEMPLATE_CACHE = {}

def load_template(path):
    if path not in _TEMPLATE_CACHE:
        tpl = cv2.imread(resource_path(path), cv2.IMREAD_COLOR)
        if tpl is None:
            raise FileNotFoundError(f'ไม่พบไฟล์เทมเพลต: {path}')
        _TEMPLATE_CACHE[path] = tpl
    return _TEMPLATE_CACHE[path]

def find_template(screen, template_path, threshold=MATCH_THRESHOLD):
    if screen is None:
        return (False, None, 0.0)
    template = load_template(template_path)
    th, tw = template.shape[:2]
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= threshold:
        center = (max_loc[0] + tw // 2, max_loc[1] + th // 2)
        return (True, center, max_val)
    return (False, None, max_val)

def _find_optional(screen, template_path, threshold=MATCH_THRESHOLD):
    if screen is None:
        return (False, None, 0.0)
    if not os.path.exists(resource_path(template_path)):
        return (False, None, 0.0)
    try:
        return find_template(screen, template_path, threshold)
    except Exception:
        return (False, None, 0.0)

def _boost_checked_green(screen, cx, cy, half=MULTI_CHECK_HALF):
    if screen is None:
        return False
    roi = screen[max(0, cy - half):cy + half, max(0, cx - half):cx + half]
    if roi.size == 0:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (35, 80, 80), (90, 255, 255))
    return float(np.count_nonzero(mask)) / mask.size >= MULTI_GREEN_THRESHOLD

def find_in_roi(screen, template_path, roi, threshold=MATCH_THRESHOLD):
    if screen is None:
        return (False, 0.0)
    x1, y1, x2, y2 = roi
    sub = screen[y1:y2, x1:x2]
    template = load_template(template_path)
    th, tw = template.shape[:2]
    if sub.shape[0] < th or sub.shape[1] < tw:
        return (False, 0.0)
    result = cv2.matchTemplate(sub, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return (max_val >= threshold, max_val)

def ensure_boosts_selected():
    print('[*] ตรวจสอบ Boost 3 ไอเทม (ตามตัวเลือกที่ติ๊กไว้)...')
    for attempt in range(3):
        screen = adb_screencap()
        all_ok = True
        for item in BOOST_ITEMS:
            want = bool(SETTINGS.get(item['key'], True))
            checked, score = find_in_roi(screen, item['check_img'], item['check_roi'], CHECK_THRESHOLD)
            if checked == want:
                print(f"    [{item['name']}] {('ติ๊กแล้ว' if want else 'ปิดอยู่')} ตรงตามที่เลือก (score={score:.2f})")
            else:
                if want:
                    print(f"    [{item['name']}] ยังไม่ติ๊ก (score={score:.2f}) -> กดเปิดใช้")
                    adb_tap(*item['tap'])
                    time.sleep(0.7)
                    all_ok = False
                else:
                    print(f"    [{item['name']}] ติ๊กค้างอยู่ แต่เลือกไม่ใช้ -> กดเอาติ๊กออก (ประหยัดเหรียญ)")
                    adb_tap(*item['tap'])
                    time.sleep(0.7)
                    all_ok = False
        if all_ok:
            print('[*] Boost ตรงตามตัวเลือกครบแล้ว')
            return
    print('[*] จบการตรวจ Boost (อาจมีบางอันของหมด)')

class State(Enum):
    REROLL = auto()
    RUN = auto()
    RESULT = auto()

def _region_gray(screen, box):
    x0, y0, x1, y1 = box
    roi = screen[max(0, y0):y1, max(0, x0):x1]
    if roi.size == 0:
        return None
    return cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32)

def _btn_green_ratio(screen, cx, cy, half=28):
    if screen is None:
        return 0.0
    roi = screen[max(0, cy - half):cy + half, max(0, cx - half):cx + half]
    if roi.size == 0:
        return 0.0
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (35, 90, 90), (75, 255, 255))
    return float(mask.mean()) / 255.0

PLAY_DIM_THRESHOLD = 110

def _play_is_dim(screen, pos):
    if screen is None or pos is None:
        return False
    x, y = pos
    roi = screen[max(0, y - 25):y + 25, max(0, x - 60):x + 60]
    if roi.size == 0:
        return False
    v = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)[:, :, 2].mean()
    return v < PLAY_DIM_THRESHOLD

def _find_green_confirm(screen, x_range=(450, 830), y_range=(415, 600), min_area=8000):
    if screen is None:
        return None
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (35, 90, 90), (75, 255, 255))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in cnts:
        a = cv2.contourArea(c)
        if a < min_area:
            continue
        x, y, w, h = cv2.boundingRect(c)
        cx, cy = (x + w // 2, y + h // 2)
        if not (x_range[0] <= cx <= x_range[1] and y_range[0] <= cy <= y_range[1]):
            continue
        if w < 150 or w > 500 or h < 40:
            continue
        if best is None or a > best[0]:
            best = (a, cx, cy)
    return (best[1], best[2]) if best else None

# --- DIGIT RECOGNITION (OCR LIGHT) ---
_DIG_GW, _DIG_GH = (24, 36)
_DIGIT_TEMPLATES = None

def _load_digit_templates():
    global _DIGIT_TEMPLATES
    if _DIGIT_TEMPLATES is None:
        _DIGIT_TEMPLATES = {}
        for d in '0123456789':
            t = cv2.imread(resource_path(f'templates/dig/{d}.png'), cv2.IMREAD_GRAYSCALE)
            if t is None:
                continue
            if t.shape != (_DIG_GH, _DIG_GW):
                t = cv2.resize(t, (_DIG_GW, _DIG_GH))
            _DIGIT_TEMPLATES[d] = t.astype(np.float32)
    return _DIGIT_TEMPLATES

def _segment_digits(crop):
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(g, 110, 255, cv2.THRESH_BINARY_INV)
    cols = th.sum(axis=0)
    groups, inrun, start = ([], False, 0)
    for x, v in enumerate(cols):
        if v > 0 and (not inrun):
            start, inrun = (x, True)
        elif v == 0 and inrun:
            groups.append((start, x))
            inrun = False
    if inrun:
        groups.append((start, len(cols)))
    boxes = []
    for x0, x1 in groups:
        rows = np.where(th[:, x0:x1].sum(axis=1) > 0)[0]
        if len(rows):
            boxes.append([x0, rows[0], x1, rows[-1] + 1])
    if not boxes:
        return (th, [])
    maxh = max((b[3] - b[1] for b in boxes))
    boxes = [b for b in boxes if b[3] - b[1] >= 0.55 * maxh]
    return (th, sorted(boxes, key=lambda b: b[0]))

# --- NEW FEATURES AUTOMATION ---

def draw_gifts_loop():
    _require_runtime_license()
    print('\n===== [ระบบของขวัญ] เริ่มสุ่มเปิดกล่องของขวัญ (กดหยุดเพื่อยกเลิก) =====')
    screen = adb_screencap()
    lf, _, _ = find_template(screen, IMG_LOBBY_PLAY)
    if not lf:
        print('[ระบบของขวัญ] ยังไม่อยู่ที่หน้าล็อบบี้หลัก -> กรุณากลับหน้าล็อบบี้ก่อนรัน')
        return
    adb_tap(*BTN_GIFT_ICON)
    time.sleep(random.uniform(1.5, 2.2))
    if not _find_optional(adb_screencap(), IMG_GIFTDRAW_TITLE, 0.8)[0]:
        print('[ระบบของขวัญ] ไม่สามารถเปิดหน้าสุ่มของขวัญได้ -> ยกเลิก')
        _escape_to_lobby()
        return
    drawn = 0
    unknown = 0
    for _ in range(GIFT_DRAW_MAX):
        if STOP_FLAG.is_set():
            print(f'[ระบบของขวัญ] สั่งหยุดทำงาน -> เปิดกล่องของขวัญไปทั้งหมด {drawn} กล่อง')
            break
        screen = adb_screencap()
        if _find_optional(screen, IMG_GIFT_PICK, 0.8)[0]:
            unknown = 0
            adb_tap(*BTN_GIFT_BOX)
            time.sleep(random.uniform(0.8, 1.3))
            adb_tap(*BTN_GIFT_SKIP)
            time.sleep(random.uniform(1.0, 1.5))
            continue
        if _btn_green_ratio(screen, *BTN_GIFT_CONFIRM) > 0.5:
            unknown = 0
            drawn += 1
            if STOP_FLAG.is_set():
                break
            print(f'[ระบบของขวัญ] สุ่มสำเร็จชิ้นที่ {drawn} -> กำลังสุ่มต่อ...')
            adb_tap(*BTN_GIFT_AGAIN)
            time.sleep(random.uniform(1.2, 1.8))
            continue
        if _btn_green_ratio(screen, *BTN_GIFT_PET) > 0.5:
            unknown = 0
            drawn += 1
            print(f'[ระบบของขวัญ] สุ่มชิ้นที่ {drawn} สำเร็จ (ได้รับสัตว์เลี้ยง!)')
            adb_tap(*BTN_GIFT_PET)
            time.sleep(random.uniform(1.2, 1.8))
            continue
        if _find_optional(screen, IMG_GIFTDRAW_TITLE, 0.8)[0]:
            unknown = 0
            adb_tap(*BTN_GIFT_DRAW)
            time.sleep(random.uniform(1.2, 1.8))
            continue
        if find_template(screen, IMG_LOBBY_PLAY)[0]:
            print('[ระบบของขวัญ] เดินทางกลับถึงล็อบบี้แล้ว -> สิ้นสุด')
            break
        unknown += 1
        if unknown >= 8:
            print('[ระบบของขวัญ] หน้าจอค้างหรือไม่พบสถานะที่รู้จัก -> สิ้นสุด')
            break
        adb_tap(*BTN_GIFT_SKIP)
        time.sleep(random.uniform(0.6, 1.0))
        adb_tap(1013, 107)
        time.sleep(random.uniform(0.8, 1.2))

    for _ in range(10):
        screen = adb_screencap()
        lf, lp, _ = find_template(screen, IMG_LOBBY_PLAY)
        if lf and (not _play_is_dim(screen, lp)):
            break
        if _find_optional(screen, IMG_GIFT_PICK, 0.8)[0]:
            adb_tap(*BTN_GIFT_BOX)
            time.sleep(random.uniform(0.8, 1.2))
            adb_tap(*BTN_GIFT_SKIP)
            time.sleep(random.uniform(1.0, 1.4))
        elif _btn_green_ratio(screen, *BTN_GIFT_CONFIRM) > 0.5:
            adb_tap(*BTN_GIFT_CONFIRM)
            time.sleep(random.uniform(1.0, 1.4))
        elif _btn_green_ratio(screen, *BTN_GIFT_PET) > 0.5:
            adb_tap(*BTN_GIFT_PET)
            time.sleep(random.uniform(1.0, 1.4))
        elif _find_optional(screen, IMG_GIFTDRAW_TITLE, 0.8)[0]:
            adb_tap(*BTN_GIFT_CLOSE)
            time.sleep(random.uniform(1.0, 1.4))
        else:
            adb_tap(*BTN_GIFT_SKIP)
            time.sleep(random.uniform(0.6, 1.0))
            adb_tap(1013, 107)
            time.sleep(random.uniform(0.8, 1.2))
    _escape_to_lobby()
    print(f'[ระบบของขวัญ] สุ่มเปิดเรียบร้อย รวมทั้งสิ้น {drawn} กล่อง -> กลับสู่ล็อบบี้')

def _side_task_progress(payload=None, **kwargs):
    event = payload if isinstance(payload, dict) else kwargs
    step = str(event.get('step') or '').strip()
    error = event.get('error')
    if not step:
        return
    suffix = f' — {error}' if error else ''
    print(f'[งานอัตโนมัติหลัง Lobby] {step}{suffix}')


def _lobby_side_tasks(screen):
    serial = str(ADB_DEVICE or '').strip()
    if not serial:
        print('[งานอัตโนมัติหลัง Lobby] ไม่พบ serial ของเครื่อง -> ข้าม Mail/Relic รอบนี้')
        return False

    tasks = []
    if bool(SETTINGS.get('use_relic', True)):
        tasks.append(('relic', relic_claim_bot.maybe_collect_relic, {}))
    if bool(SETTINGS.get('use_mail_lives', False)):
        tasks.append(('mail_lives', mail_lives_bot.maybe_collect_mail_lives, {'min_count': MAIL_MIN_COUNT}))
    if not tasks:
        return False

    side_task_adb.ADB_PATH = ADB_PATH
    side_task_adb.register_device_stop_event(serial, STOP_FLAG)
    acted = False
    current_screen = screen
    try:
        for name, func, task_settings in tasks:
            if STOP_FLAG.is_set():
                break
            try:
                result = func(
                    serial,
                    screen=current_screen,
                    stop_event=STOP_FLAG,
                    progress_callback=_side_task_progress,
                    settings=task_settings,
                )
            except Exception as exc:
                acted = True
                print(f"[งานอัตโนมัติหลัง Lobby] AutoFarm side task warning: {name} — {side_task_adb.describe_error(exc)}")
                current_screen = adb_screencap()
                continue

            details = dict(getattr(result, 'details', {}) or {})
            skipped = bool(details.get('skipped'))
            reason = details.get('reason') if skipped else None
            reason_text = f' (reason={reason})' if reason else ''
            print(f"[งานอัตโนมัติหลัง Lobby] AutoFarm side task '{name}': {result.message}{reason_text}")

            if not skipped and result.status != side_runtime.AutomationStatus.NOT_READY:
                acted = True
            if result.status == side_runtime.AutomationStatus.CANCELLED:
                break
            current_screen = adb_screencap()
    finally:
        side_task_adb.unregister_device_stop_event(serial, STOP_FLAG)
    return acted

def _escape_to_lobby(max_tries=8):
    for _ in range(max_tries):
        if STOP_FLAG.is_set():
            return
        screen = adb_screencap()
        lf, lp, _ = find_template(screen, IMG_LOBBY_PLAY)
        if lf and (not _play_is_dim(screen, lp)):
            return
        acted = False
        gpos = _find_green_confirm(screen)
        if gpos:
            print(f'[ระบบนำทาง] ตรวจพบปุ่มสีเขียวยืนยันกลางหน้าจอที่พิกัด {gpos} -> กดเคลียร์หน้าจอ')
            adb_tap(*gpos)
            acted = True
        elif dismiss_unknown_popup(screen):
            acted = True
        if not acted:
            return
        time.sleep(random.uniform(0.8, 1.2))

def dismiss_unknown_popup(screen, allow_fallback=False):
    if screen is None:
        return False
    xf, xp, xsc = _find_optional(screen, IMG_GENERIC_CLOSE, GENERIC_CLOSE_THRESHOLD)
    if xf:
        print(f'[ระบบนำทาง] ตรวจพบป๊อปอัปโฆษณาแทรกซ้อน -> ทำการปิดที่พิกัด {xp} (ความมั่นใจ={xsc:.2f})')
        adb_tap(*xp)
        human_sleep(0.9)
        return True
    if allow_fallback:
        for fx, fy in GENERIC_CLOSE_FALLBACK:
            print(f'[ระบบนำทาง] หน้าจอไม่ตอบสนองชั่วคราว -> พยายามกดตำแหน่งฉุกเฉิน ({fx},{fy})')
            adb_tap(fx, fy)
            human_sleep(0.6)
        return True
    return False

def ensure_on_boost_screen(max_tries=15):
    x_close_tries = 0
    side_budget = 1
    for i in range(max_tries):
        if STOP_FLAG.is_set():
            return False
        screen = adb_screencap()
        dismissed = False
        for pop in DISMISS_POPUPS:
            pf, _, psc = find_template(screen, pop['img'], pop['th'])
            if pf:
                if x_close_tries < 3:
                    print(f"[ระบบนำทาง] ตรวจพบป๊อปอัป {pop['name']} (ความมั่นใจ={psc:.2f}) -> กดปิดที่พิกัด {pop['x']}")
                    adb_tap(*pop['x'])
                    x_close_tries += 1
                    human_sleep(0.9)
                else:
                    print(f"[ระบบนำทาง] ไม่สามารถปิดหน้าต่าง {pop['name']} ได้หลังลองหลายครั้ง -> ยุติเพื่อความปลอดภัย")
                    human_sleep(0.8)
                dismissed = True
                break
        if dismissed:
            continue
        
        x_close_tries = 0
        lf, lp, _ = find_template(screen, IMG_LOBBY_PLAY)
        if lf and _play_is_dim(screen, lp):
            print('[ระบบนำทาง] จอล็อบบี้ถูกหรี่แสงมืด -> ตรวจพบป๊อปอัปบดบัง กำลังค้นหาปุ่มปิด')
            lf = False
            
        if not lf:
            if SETTINGS['avoid_revive']:
                pf, _, psc = _find_optional(screen, IMG_PITLIFT, PITLIFT_THRESHOLD)
                if pf:
                    if BTN_PITLIFT_NO:
                        print(f'[ระบบนำทาง] ตรวจพบกล่องชุบชีวิตเสียคริสตัล (Pit Lift) -> กดปฏิเสธทันทีเพื่อป้องกันการเสียคริสตัล')
                        adb_tap(*BTN_PITLIFT_NO)
                    else:
                        print(f'[ระบบนำทาง] ตรวจพบกล่องชุบชีวิตเสียคริสตัล (Pit Lift) -> รอระบบปฏิเสธเอง')
                    human_sleep(1.2)
                    continue
            bf, _, bsc = _find_optional(screen, IMG_BAKERY_TITLE, BAKERY_THRESHOLD)
            if bf:
                print(f'[ระบบนำทาง] ตรวจพบหน้าต่าง Fortune Bakery (เตาอบ) -> กดปิดด้วย X ป้องกันการเสียคริสตัล')
                adb_tap(*BTN_BAKERY_CLOSE)
                human_sleep(1.2)
                continue
            dismissed_confirm = False
            for cp in CONFIRM_POPUPS:
                cf, _, csc = find_template(screen, cp['img'], cp['th'])
                if cf:
                    print(f"[ระบบนำทาง] ตรวจพบหน้าต่าง {cp['name']} -> กดยืนยันป๊อปอัปที่พิกัด {cp['btn']}")
                    adb_tap(*cp['btn'])
                    human_sleep(1.2)
                    dismissed_confirm = True
                    break
            if dismissed_confirm:
                continue
            if dismiss_unknown_popup(screen):
                continue
                
        x_close_tries = 0
        found, _, _ = find_template(screen, IMG_BOOST_SCREEN)
        if found:
            if i > 0:
                print('[ระบบนำทาง] เข้าสู่หน้าเตรียมตัววิ่งเรียบร้อย')
            return True
        else:
            okf, okp, _ = find_template(screen, IMG_OK_BUTTON)
            if okf:
                print('[ระบบนำทาง] ค้างอยู่ที่หน้าต่างสรุปคะแนน -> กด OK')
                adb_tap(*okp)
                human_sleep(2.5)
            else:
                if lf:
                    if side_budget > 0 and _lobby_side_tasks(screen):
                        side_budget -= 1
                        continue
                    print(f'[ระบบนำทาง] หน้าจอหลักเรียบร้อยดี (ครั้งที่ {i + 1}) -> กดเริ่มเกมเพื่อเข้าหน้าเตรียมวิ่ง')
                    adb_tap(*lp)
                    human_sleep(DELAY_AFTER_PLAY)
                else:
                    if not dismiss_unknown_popup(screen):
                        gpos = _find_green_confirm(screen)
                        if gpos:
                            print(f'[ระบบนำทาง] ตรวจพบปุ่มสีเขียวยืนยันกลางหน้าจอที่พิกัด {gpos} -> กดเคลียร์หน้าจอ')
                            adb_tap(*gpos)
                            human_sleep(1.2)
                        else:
                            print(f'[ระบบนำทาง] มีหน้าต่างอื่นบดบังอยู่ -> พยายามกดยืนยันจุดเคลียร์หน้าจอ 2 จุด')
                            adb_tap(*BTN_POPUP_CONFIRM)
                            human_sleep(0.4)
                            adb_tap(*BTN_POPUP_CONFIRM_LOW)
                            human_sleep(1.2)
                            if i >= max_tries - 3:
                                dismiss_unknown_popup(screen, allow_fallback=True)
    print('[ระบบนำทาง] ⚠️ ไม่สามารถเข้าสู่หน้าเตรียมตัวได้ในเวลาที่กำหนด')
    return False

def multibuy_until_target():
    print('[reroll] เลือกกล่อง Random Boost ก่อน')
    adb_tap(*BTN_BOX)
    human_sleep(0.8)
    print('[reroll] เปิดหน้า Multi (เลือกบูสต์ที่ต้องการ)')
    adb_tap(*BTN_MULTI)
    human_sleep(1.0)
    if not any((SETTINGS.get('multi_' + b['key'], b['default']) for b in MULTI_BOOSTS)):
        SETTINGS['multi_double_coins'] = True
        print('[reroll] ไม่ได้เลือกบูสต์ Multi-Buy เลย -> ใช้ Double Coins เป็นค่าเริ่มต้น')
    dlg = adb_screencap()
    for b in MULTI_BOOSTS:
        cx, cy = b['pos']
        want = bool(SETTINGS.get('multi_' + b['key'], b['default']))
        checked = _boost_checked_green(dlg, cx, cy)
        if checked == want:
            continue
        action = 'กดติ๊ก' if want else 'กดเอาออก'
        print(f"    [{b['name']}] {action}")
        adb_tap(cx, cy)
        human_sleep(0.4)
    print('[reroll] กด Multi-Buy -> ให้เกมสุ่มซื้อเองจนได้บูสต์ที่เลือก')
    adb_tap(*BTN_MULTI_BUY)
    start = time.time()
    saw_rolling = False
    while time.time() - start < MULTIBUY_TIMEOUT:
        if STOP_FLAG.is_set():
            return False
        time.sleep(0.5)
        screen = adb_screencap()
        rolling, _, _ = find_template(screen, IMG_MULTIBUY_STOP, MULTIBUY_STOP_THRESHOLD)
        if rolling:
            saw_rolling = True
            continue
        if saw_rolling:
            print('[reroll] สุ่มบูสต์เสร็จแล้ว (ปุ่ม Stop หาย)')
            human_sleep(0.8)
            return True
        if find_template(screen, IMG_TARGET_ITEM)[0]:
            print('[reroll] ได้ Double Coins แล้ว')
            return True
        if time.time() - start > 4.0 and find_template(screen, IMG_BOOST_SCREEN)[0]:
            print('[reroll] ไม่พบการสุ่ม (อาจเหรียญไม่พอ/จบทันที) -> ไปต่อ')
            return True
    print('[reroll] หมดเวลา Multi-Buy -> ปิดหน้า Multi')
    adb_tap(*BTN_MULTI_CLOSE)
    human_sleep(1.0)
    return False

# --- STATE MACHINE CONTROLS ---

def state_reroll():
    print('\n===== [STATE 1] REROLL — Multi-Buy สุ่มบูสต์ที่เลือก =====')
    if not ensure_on_boost_screen():
        print('[WARN] นำทางยังไม่สำเร็จ -> รอแล้ววนลองใหม่ (ไม่หยุดบอท)')
        human_sleep(3.0)
        return State.REROLL
    screen = adb_screencap()
    found, _, score = find_template(screen, IMG_TARGET_ITEM)
    if found and SETTINGS.get('multi_double_coins', True):
        print(f'[OK] มี Double Coins อยู่แล้ว (score={score:.3f}) -> ข้ามการสุ่ม')
    else:
        if not SETTINGS['use_multibuy']:
            print('[set] ปิดการสุ่มบูสต์ (Multi-Buy) ไว้ -> เข้าเล่นเลย (บูสต์ที่เลือกจะไม่ถูกสุ่ม)')
        elif not multibuy_until_target():
            print('[WARN] Multi-Buy ไม่สำเร็จ -> วนกลับมานำทาง/ลองใหม่ (ไม่หยุดบอท)')
            return State.REROLL
    ensure_boosts_selected()
    print('[OK] -> กด Play เริ่มวิ่ง')
    adb_tap(*BTN_PLAY)
    human_sleep(DELAY_AFTER_PLAY)
    return State.RUN

def _pattern_path():
    return os.path.join(_writable_dir(), PATTERN_FILE)

def load_pattern():
    try:
        data = json.load(open(_pattern_path(), encoding='utf-8'))
        evs = data.get('events', data) if isinstance(data, dict) else data
        return [[float(t), str(a)] for t, a in evs] if evs else None
    except Exception:
        return None

def save_pattern(events):
    json.dump({'events': events}, open(_pattern_path(), 'w', encoding='utf-8'))

def wait_ingame(timeout=20.0):
    start = time.time()
    while time.time() - start < timeout:
        if STOP_FLAG.is_set():
            return False
        f, _, _ = find_template(adb_screencap(), IMG_INGAME, INGAME_THRESHOLD)
        if f:
            return True
        time.sleep(0.12)
    return False

def _frame_signature(screen):
    small = cv2.resize(screen, (64, 36))
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)

def state_run():
    global CAPTCHA_CHECK_ENABLED
    CAPTCHA_CHECK_ENABLED = False
    pattern = REPLAY_PATTERN
    run_mode = configured_run_mode()
    jump_stop = threading.Event()
    action_count = [0]
    worker_loop = None
    if pattern:
        print(f'\n===== [STATE 2] RUN — โหมด PATTERN ({len(pattern)} การกด) + คอยกด relay =====')
        print('[replay] รอเข้าหน้าวิ่ง (BONUSTIME) เพื่อตั้ง t=0 ...')
        wait_ingame()
        t0 = time.time()
        def worker_loop():
            for t_at, action in pattern:
                if jump_stop.is_set() or STOP_FLAG.is_set():
                    return None
                while t_at - (time.time() - t0) > 0:
                    if jump_stop.is_set() or STOP_FLAG.is_set():
                        return None
                    time.sleep(min(t_at - (time.time() - t0), 0.04))
                if _IN_CAPTCHA_SOLVER and _wait_while_captcha(jump_stop):
                    return None
                if action == 'slide':
                    threading.Thread(target=adb_slide, daemon=True).start()
                else:
                    adb_tap(*BTN_JUMP, jitter=JUMP_JITTER)
                action_count[0] += 1
            print(f'[replay] เล่นซ้ำ pattern ครบ {action_count[0]} การกดแล้ว (รอจบรอบ)')
    else:
        if run_mode != 'none':
            print(f'\n===== [STATE 2] RUN — โหมด {run_mode} + คอยกด relay =====')
            def worker_loop():
                while not jump_stop.is_set() and (not STOP_FLAG.is_set()):
                    if _IN_CAPTCHA_SOLVER:
                        if _wait_while_captcha(jump_stop):
                            return None
                        continue
                    action = perform_run_action(run_mode)
                    action_count[0] += 1
                    if not wait_action_delay(jump_stop, action):
                        return None
        else:
            print('\n===== [STATE 2] RUN — ไม่กดกระโดด/สไลด์อัตโนมัติ + คอยกด relay เท่านั้น =====')

    start_time = time.time()
    jt = None
    if worker_loop is not None:
        jt = threading.Thread(target=worker_loop, daemon=True)
        jt.start()
    last_sig = None
    last_change = time.time()
    try:
        while not STOP_FLAG.is_set():
            t = time.time() - start_time
            screen = adb_screencap()
            if PREVENT_INACTIVE and screen is not None:
                sig = _frame_signature(screen)
                if last_sig is not None and float(np.mean(np.abs(sig - last_sig))) < FREEZE_DIFF:
                    if time.time() - last_change >= FREEZE_SECS:
                        print('[recover] หน้าจอค้าง/ป๊อปอัป (inactive?) -> กด Confirm กลางจอเพื่อวิ่งต่อ')
                        adb_tap(*BTN_INACTIVE_CONFIRM)
                        human_sleep(1.2)
                        last_sig = None
                        last_change = time.time()
                        continue
                else:
                    last_change = time.time()
                last_sig = sig
            if SETTINGS['use_faststart'] and t < FASTSTART_WINDOW:
                fs, _, fssc = _find_optional(screen, IMG_FASTSTART, FASTSTART_THRESHOLD)
                if fs:
                    print(f'    [faststart] เจอปุ่มวิ่งบูส Fast Start (score={fssc:.3f}) -> กดใช้')
                    adb_tap(*BTN_FASTSTART)
                    human_sleep(0.5)
                    continue
            found_relay, rpos, rscore = find_template(screen, IMG_RELAY, RELAY_THRESHOLD)
            if found_relay:
                if SETTINGS['use_relay']:
                    print(f'    [relay] เจอนินจา (score={rscore:.3f}) -> กดวิ่งต่อ')
                    adb_tap(*BTN_RELAY)
                    human_sleep(0.5)
                    continue
                else:
                    print(f'    [relay] เจอนินจา (score={rscore:.3f}) แต่ปิดใช้นินจาไว้ -> ปล่อยจบรอบ')
            found_result, _, sscore = find_template(screen, IMG_RESULT)
            if found_result:
                print(f'[OK] เจอหน้า Result (score={sscore:.3f}) หลังทำ Action {action_count[0]} ครั้ง -> STATE 3')
                return State.RESULT
            if t >= RUN_STATE_TIMEOUT:
                print(f'[WARN] State 2 เกินเวลา {RUN_STATE_TIMEOUT}s -> บังคับไป STATE 3')
                return State.RESULT
            time.sleep(RESULT_CHECK_INTERVAL)
    finally:
        jump_stop.set()
        CAPTCHA_CHECK_ENABLED = True

COIN_LOG_ROI = (945, 383, 1118, 430)
COIN_TOTAL = 0
COIN_CALLBACK = None
COIN_LOG_SCREEN = None

def _writable_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _coin_log_dir():
    base = os.path.join(_writable_dir(), 'coin_logs')
    screen = str(COIN_LOG_SCREEN or '').strip()
    if not screen:
        return base
    safe_screen = ''.join(ch if ch.isalnum() or ch in ('-', '_', '.') else '_' for ch in screen)
    return os.path.join(base, safe_screen)

def read_coins(screen):
    if screen is None:
        return None
    tpls = _load_digit_templates()
    if len(tpls) < 10:
        return None
    try:
        x1, y1, x2, y2 = COIN_LOG_ROI
        th, boxes = _segment_digits(screen[y1:y2, x1:x2])
        if not boxes:
            return None
        out = ""
        for b in boxes:
            g = cv2.resize(th[b[1]:b[3], b[0]:b[2]], (_DIG_GW, _DIG_GH)).astype(np.float32)
            best, bestsc = None, -1.0
            for ch, t in tpls.items():
                r = cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)[0][0]
                if r > bestsc:
                    bestsc, best = r, ch
            if bestsc < 0.3:
                return None
            out += best
        return int(out) if out else None
    except Exception as e:
        print(f"[coins] อ่านเลขไม่สำเร็จ: {e}")
        return None

def record_result_coins(screen):
    global COIN_TOTAL
    if screen is None:
        return
    coins = read_coins(screen)
    if coins is not None:
        COIN_TOTAL += coins
    try:
        log_dir = _coin_log_dir()
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        with open(os.path.join(log_dir, 'coins.csv'), 'a', encoding='utf-8') as f:
            f.write(f"{ts},{(coins if coins is not None else '')},{COIN_TOTAL}\n")
        if coins is not None:
            print(f'[coins] เหรียญรอบนี้: {coins:,}  (รวม {COIN_TOTAL:,})')
        else:
            print('[coins] อ่านเลขเหรียญไม่ได้')
    except Exception as e:
        print(f'[coins] บันทึกไม่สำเร็จ: {e}')
    if COIN_CALLBACK is not None:
        try:
            COIN_CALLBACK(coins, COIN_TOTAL)
        except Exception:
            pass

def state_result():
    print('\n===== [STATE 3] RESULT — กำลังหาปุ่ม OK =====')
    attempts = 0
    MAX_ATTEMPTS = 40
    while not STOP_FLAG.is_set():
        screen = adb_screencap()
        found, pos, score = find_template(screen, IMG_OK_BUTTON)
        if found:
            record_result_coins(screen)
            human_sleep(1.5)
            print(f'[OK] เจอปุ่ม OK (score={score:.3f}) -> กดกลับล็อบบี้')
            adb_tap(*pos)
            human_sleep(2.5)
            return State.REROLL
        attempts += 1
        if attempts >= MAX_ATTEMPTS:
            print('[WARN] หาปุ่ม OK ไม่เจอเกินกำหนด -> วนกลับ STATE 1 (ให้ตัวนำทางจัดการ)')
            return State.REROLL
        print(f'[..] ยังไม่เจอปุ่ม OK (best score={score:.3f}) attempt {attempts}/{MAX_ATTEMPTS}')
        time.sleep(LOOP_SLEEP)
    return None

def check_connection():
    if ADB_DEVICE:
        if ':' in str(ADB_DEVICE):
            try:
                _run([ADB_PATH, 'connect', str(ADB_DEVICE)], timeout=4)
            except Exception:
                pass
    else:
        auto_connect_emulators()
        auto_select_device()
    return adb_screencap() is not None

def run_state_machine(max_loops=0, on_loop_done=None):
    global COIN_TOTAL
    _require_runtime_license()
    COIN_TOTAL = 0
    current_state = State.REROLL
    loops_done = 0
    err_streak = 0
    try:
        while not STOP_FLAG.is_set():
            prev = current_state
            try:
                if current_state == State.REROLL:
                    current_state = state_reroll()
                elif current_state == State.RUN:
                    current_state = state_run()
                elif current_state == State.RESULT:
                    current_state = state_result()
                err_streak = 0
            except Exception as e:
                err_streak += 1
                print(f'[ERR] ข้อผิดพลาดใน {prev} (ครั้งที่ {err_streak}) -> ข้ามแล้วลองใหม่: {e}')
                if not getattr(sys, 'frozen', False):
                    print(traceback.format_exc())
                if err_streak >= 30:
                    print('[FATAL] ผิดพลาดติดกันเยอะมาก -> หยุด (เช็ก LDPlayer/ADB ว่ายังเปิดอยู่ไหม)')
                    break
                human_sleep(1.5)
                current_state = State.REROLL
                continue
            if prev == State.RESULT and current_state == State.REROLL:
                loops_done += 1
                msg = f'[loop] เล่นจบรอบที่ {loops_done}'
                if max_loops:
                    msg += f' / {max_loops}'
                print(msg)
                if on_loop_done is not None:
                    try:
                        on_loop_done(loops_done)
                    except Exception:
                        pass
                if max_loops and loops_done >= max_loops:
                    print(f'[loop] ครบ {max_loops} รอบแล้ว -> หยุดบอท')
                    break
            if current_state is None:
                break
    except KeyboardInterrupt:
        print('\n[!] Ctrl+C — หยุดบอท')
    finally:
        STOP_FLAG.set()
        print('\n===== บอทหยุดทำงานแล้ว =====')

# --- SEND HEARTS (BETA) ---

def _wait_friend_popup(pos, tries=5):
    for _ in range(tries):
        if STOP_FLAG.is_set():
            return False
        screen = adb_screencap()
        if screen is not None and _btn_green_ratio(screen, pos[0], pos[1]) > FRIEND_POPUP_GREEN_MIN:
            return True
        time.sleep(random.uniform(0.22, 0.4))
    return False

def _friend_send_active(screen, y, x=BTN_FRIEND_SEND_X, half=32):
    if screen is None:
        return False
    y1, y2 = (max(0, y - half), min(screen.shape[0], y + half))
    x1, x2 = (max(0, x - half), min(screen.shape[1], x + half))
    roi = screen[y1:y2, x1:x2]
    if roi.size == 0:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 120, 90), (10, 255, 255)) | cv2.inRange(hsv, (170, 120, 90), (180, 255, 255))
    grn = cv2.inRange(hsv, (35, 80, 80), (85, 255, 255))
    area = roi.shape[0] * roi.shape[1]
    red_ratio = float(red.sum()) / 255.0 / area
    grn_ratio = float(grn.sum()) / 255.0 / area
    if not (red_ratio > FRIEND_SEND_RED_MIN and grn_ratio > FRIEND_SEND_GREEN_MIN):
        return False
    h, w = screen.shape[:2]
    ay1, ay2 = (max(0, y - FRIEND_ARROW_HALF), min(h, y + FRIEND_ARROW_HALF))

    def _yellow(x1c, x2c):
        x1c, x2c = (max(0, x1c), min(w, x2c))
        r = screen[ay1:ay2, x1c:x2c]
        if r.size == 0:
            return 0.0
        hh = cv2.cvtColor(r, cv2.COLOR_BGR2HSV)
        yl = cv2.inRange(hh, (20, 120, 120), (35, 255, 255))
        return float(yl.sum()) / 255.0 / (r.shape[0] * r.shape[1])

    strip = screen[max(0, y - 14):min(h, y + 14), 150:620]
    if strip.size:
        sh = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
        syl = cv2.inRange(sh, (20, 120, 120), (35, 255, 255))
        if float(syl.sum()) / 255.0 / (strip.shape[0] * strip.shape[1]) > FRIEND_SELF_HILITE_MIN:
            return False
    yellow_arrow = _yellow(x + 2, x + 50)
    yellow_left = _yellow(x - 50, x - 2)
    return yellow_arrow > FRIEND_ARROW_YELLOW_MIN and yellow_arrow - yellow_left > FRIEND_ARROW_DIFF_MIN

def _topmost_send_button(screen, half=22, step=12):
    if screen is None:
        return None
    run = []
    for y in range(298, 646, step):
        if _friend_send_active(screen, y, half=half):
            run.append(y)
        else:
            if run:
                return sum(run) // len(run)
    return sum(run) // len(run) if run else None

def _tap_burst(x, y, n=3, gap=0.08):
    for _ in range(n):
        adb_tap(x, y)
        time.sleep(gap)

def send_hearts_loop():
    _require_runtime_license()
    print("\n===== [SendHearts] ส่งหัวใจให้เพื่อน (Beta) =====")
    screen = adb_screencap()
    if screen is not None and _find_optional(screen, IMG_FRIEND_POPUP, 0.8)[0]:
        adb_tap(*BTN_FRIEND_INFO_CLOSE)
        time.sleep(random.uniform(0.5, 0.8))
        screen = adb_screencap()
    if screen is None or not _find_optional(screen, IMG_FRIENDS_HEADER, 0.72)[0]:
        print("[hearts] ไม่ได้อยู่หน้า Friends leaderboard -> ไปล็อบบี้ (แท็บ Friends) ก่อนแล้วกดใหม่")
        return
    rx1, ry1, rx2, ry2 = FRIEND_LIST_REGION
    print("[hearts] ⏳ กำลังเลื่อนลิสต์ขึ้นบนสุดก่อน (อันดับ 1) แล้วจะเริ่มส่ง — ช่วงนี้ยังไม่ส่ง รอสักครู่...")
    for i in range(60):
        if STOP_FLAG.is_set():
            break
        s1 = _frame_signature(screen[ry1:ry2, rx1:rx2]) if screen is not None else None
        adb_swipe(420, 320, 420, 605, 300)
        time.sleep(random.uniform(0.3, 0.5))
        screen = adb_screencap()
        if screen is None:
            break
        s2 = _frame_signature(screen[ry1:ry2, rx1:rx2])
        if s1 is not None and float(np.mean(np.abs(s2 - s1))) < 2.5:
            break
        if (i + 1) % 8 == 0:
            print(f"[hearts]    ...ยังเลื่อนขึ้นอยู่ ({i + 1} ครั้ง)")
    if STOP_FLAG.is_set():
        print("[hearts] หยุดตามคำสั่ง (ระหว่างเลื่อนขึ้น) — ยังไม่ได้ส่ง")
        return
    print("[hearts] ✅ ถึงบนสุดแล้ว — เริ่มส่งหัวใจจากอันดับ 1 ลงล่างไปเรื่อยๆ")
    sent = 0
    for _ in range(SEND_HEARTS_MAX_SCROLLS):
        if STOP_FLAG.is_set():
            print(f"[hearts] หยุดตามคำสั่ง — ส่งไป {sent} คน")
            break
        screen = adb_screencap()
        if screen is not None:
            if _btn_green_ratio(screen, *BTN_FRIEND_CONFIRM) > FRIEND_POPUP_GREEN_MIN:
                adb_tap(*BTN_FRIEND_CANCEL)
                time.sleep(random.uniform(0.4, 0.6))
            else:
                if _btn_green_ratio(screen, *BTN_FRIEND_SENT_OK) > FRIEND_POPUP_GREEN_MIN:
                    adb_tap(*BTN_FRIEND_SENT_OK)
                    time.sleep(random.uniform(0.4, 0.6))
                else:
                    if _find_optional(screen, IMG_FRIEND_POPUP, 0.8)[0]:
                        adb_tap(*BTN_FRIEND_INFO_CLOSE)
                        time.sleep(random.uniform(0.4, 0.6))
        for _ in range(6):
            if STOP_FLAG.is_set():
                break
            screen = adb_screencap()
            if screen is None:
                break
            ty = _topmost_send_button(screen)
            if ty is None:
                break
            adb_tap(BTN_FRIEND_SEND_X, ty)
            time.sleep(random.uniform(0.3, 0.5))
            if not _wait_friend_popup(BTN_FRIEND_CONFIRM):
                break
            adb_tap(*BTN_FRIEND_CONFIRM)
            sent += 1
            if sent % 20 == 0:
                print(f"[hearts] ส่งแล้ว {sent} คน...")
            if _wait_friend_popup(BTN_FRIEND_SENT_OK):
                adb_tap(*BTN_FRIEND_SENT_OK)
            time.sleep(random.uniform(0.35, 0.55))
        adb_swipe(*FRIEND_SCROLL, 420)
        time.sleep(random.uniform(0.6, 0.85))
        screen = adb_screencap()
        if screen is not None and _find_optional(screen, IMG_FRIEND_POPUP, 0.8)[0]:
            adb_tap(*BTN_FRIEND_INFO_CLOSE)
            time.sleep(random.uniform(0.4, 0.6))
    screen = adb_screencap()
    if screen is not None and _find_optional(screen, IMG_FRIEND_POPUP, 0.8)[0]:
        adb_tap(*BTN_FRIEND_INFO_CLOSE)
        time.sleep(random.uniform(0.4, 0.6))
    print(f"[hearts] จบ — ส่งหัวใจ {sent} คน")


# --- TREASURE EXTRACT (BETA) ---

def _read_tr_number(screen, roi):
    if screen is None:
        return None
    tpls = _load_digit_templates()
    if len(tpls) < 10:
        return None
    x1, y1, x2, y2 = roi
    if y2 > screen.shape[0] or x2 > screen.shape[1]:
        return None
    g = cv2.cvtColor(screen[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(g, TR_DIG_THR, 255, cv2.THRESH_BINARY_INV)
    cols = th.sum(axis=0)
    groups, inrun, st = ([], False, 0)
    for x, v in enumerate(cols):
        if v > 0 and (not inrun):
            st, inrun = (x, True)
        else:
            if v == 0 and inrun:
                groups.append((st, x))
                inrun = False
    if inrun:
        groups.append((st, len(cols)))
    boxes = []
    for a, b in groups:
        rows = np.where(th[:, a:b].sum(axis=1) > 0)[0]
        if len(rows) and rows[-1] - rows[0] >= 12 and (b - a >= 4):
            boxes.append((a, rows[0], b, rows[-1] + 1))
    if not boxes:
        return None
    out = ""
    for bx0, by0, bx1, by1 in boxes:
        gl = cv2.resize(th[by0:by1, bx0:bx1], (_DIG_GW, _DIG_GH)).astype(np.float32)
        best, sc = ("?", -1.0)
        for ch, t in tpls.items():
            r = cv2.matchTemplate(gl, t, cv2.TM_CCOEFF_NORMED)[0][0]
            if r > sc:
                sc, best = (r, ch)
        if best == "?" or sc < 0.3:
            return None
        out += best
    try:
        return int(out)
    except ValueError:
        return None

def _read_powder(screen):
    return _read_tr_number(screen, TR_POWDER_ROI)

def _tr_cancel_extract():
    adb_tap(*BTN_TR_EXTRACT_CLOSE)
    time.sleep(random.uniform(1.2, 1.8))

def _tr_goto_extract_grid():
    for _ in range(3):
        if STOP_FLAG.is_set():
            return False
        adb_tap(*BTN_TR_CABINET)
        time.sleep(random.uniform(1.8, 2.2))
        screen = adb_screencap_stable()
        if screen is not None:
            if _find_optional(screen, IMG_TR_CABINET_TITLE, 0.85)[0]:
                return True
            if _find_optional(screen, IMG_TR_EXPAND_POPUP, 0.8)[0]:
                print("[treasure] เจอป๊อปอัป 'ตู้เต็ม/ขยายตู้' -> ปิด (ไม่ขยาย) แล้วลองเข้าตู้ใหม่")
                adb_tap(*BTN_TR_EXPAND_CLOSE)
                time.sleep(random.uniform(1.2, 1.6))
    return False

def _draw_and_extract_loop_legacy():
    _require_runtime_license()
    print("\n===== [Treasure] สุ่ม+ย่อยสมบัติ (Beta) =====")
    print("*** เตือน: ล็อกดาว (⭐) สมบัติที่อยากเก็บให้ครบก่อน! ที่ไม่ล็อก = บอทย่อยได้ ***")
    screen = adb_screencap_stable()
    if screen is None or not _find_optional(screen, IMG_TR_DRAW_TITLE, 0.85)[0]:
        print("[treasure] ไม่ได้อยู่หน้า 'Treasure Draw' -> เปิดหน้าสุ่มสมบัติก่อน (ล็อบบี้ -> Treasure -> Draw) แล้วกดใหม่")
        return
    drawn = extracted = 0
    draw_fail = 0
    for _ in range(TR_MAX_CYCLES):
        if STOP_FLAG.is_set():
            print(f"[treasure] หยุดตามคำสั่ง — สุ่ม {drawn} / ย่อย {extracted}")
            break
        screen = adb_screencap_stable()
        if screen is None or not _find_optional(screen, IMG_TR_DRAW_TITLE, 0.85)[0]:
            print("[treasure] หลุดจากหน้า Draw (นำทางผิด) -> หยุด")
            break
        adb_tap(*BTN_TR_NORMAL)
        time.sleep(random.uniform(1.8, 2.4))
        got_reveal = False
        for _ in range(7):
            if STOP_FLAG.is_set():
                break
            adb_tap(*BTN_TR_CHEST)
            time.sleep(random.uniform(1.1, 1.5))
            screen = adb_screencap_stable()
            if screen is not None and _find_optional(screen, IMG_TR_RECEIVED, 0.8)[0]:
                got_reveal = True
                break
        if got_reveal:
            drawn += 1
            draw_fail = 0
            adb_tap(*BTN_TR_REVEAL_CONFIRM)
            time.sleep(random.uniform(1.6, 2.2))
        else:
            draw_fail += 1
            print(f"[treasure] สุ่มไม่สำเร็จ (ครั้งที่ {draw_fail}) — ตู้อาจเต็ม/เหรียญไม่พอ")
            if draw_fail >= 2:
                print("[treasure] สุ่มไม่ได้ติดกัน 2 ครั้ง (แม้ย่อยเคลียร์ที่แล้ว) = เหรียญหมด -> หยุด")
                break
        if not _tr_goto_extract_grid():
            print("[treasure] เข้าหน้าตู้ไม่สำเร็จ -> หยุด")
            break
        adb_tap(*BTN_TR_EXTRACT_ENTER)
        time.sleep(random.uniform(1.8, 2.4))
        screen = adb_screencap_stable()
        if screen is None or not _find_optional(screen, IMG_TR_EXTRACT_TITLE, 0.85)[0]:
            print("[treasure] เข้าโหมด Extract ไม่สำเร็จ -> หยุด")
            break
        adb_tap(*BTN_TR_SORT)
        time.sleep(random.uniform(1.0, 1.4))
        adb_tap(*BTN_TR_SORT_TIER)
        time.sleep(random.uniform(1.2, 1.6))
        adb_tap(*BTN_TR_TOPLEFT)
        time.sleep(random.uniform(1.2, 1.6))
        screen = adb_screencap_stable()
        powder = _read_powder(screen)
        if powder is None:
            print("[treasure] อ่านค่า powder ไม่ได้ -> ยกเลิก+หยุด (fail-safe ไม่ย่อยตอนไม่แน่ใจ)")
            _tr_cancel_extract()
            break
        if powder == 0:
            print("[treasure] selected top slot has no extractable junk -> flip tier sort direction and retry once")
            adb_tap(*BTN_TR_SORT)
            time.sleep(random.uniform(1.0, 1.4))
            adb_tap(*BTN_TR_SORT_TIER)
            time.sleep(random.uniform(1.2, 1.6))
            adb_tap(*BTN_TR_TOPLEFT)
            time.sleep(random.uniform(1.2, 1.6))
            screen = adb_screencap_stable()
            powder = _read_powder(screen)
            if powder is None:
                print("[treasure] powder unreadable after sort retry -> cancel+stop (fail-safe)")
                _tr_cancel_extract()
                break
            if powder > TR_POWDER_MAX:
                print(f"[treasure] powder={powder} > {TR_POWDER_MAX} after sort retry -> cancel+stop")
                _tr_cancel_extract()
                break
        if powder == 0:
            print("[treasure] เลือกไม่ติด (ชิ้นบนสุดถูกล็อก⭐/ใส่อยู่ = ไม่มีขยะให้ย่อย) -> ยกเลิก+หยุด")
            _tr_cancel_extract()
            break
        if powder > TR_POWDER_MAX:
            print(f"[treasure] powder={powder} > {TR_POWDER_MAX} = ของมีค่า/ขยะหมดแล้ว -> ยกเลิก+หยุด (ไม่ย่อยของแพง)")
            _tr_cancel_extract()
            break
        print(f"[treasure] ย่อยขยะ (powder={powder}, tier ต่ำสุด, ปลอดภัย)")
        adb_tap(*BTN_TR_EXTRACT_GO)
        time.sleep(random.uniform(1.4, 1.8))
        screen = adb_screencap_stable()
        if screen is None or not _find_optional(screen, IMG_TR_EXTRACT_CONFIRM, 0.8)[0]:
            print("[treasure] ไม่เห็นหน้ายืนยัน Extract -> หยุด")
            break
        adb_tap(*BTN_TR_EXTRACT_CONFIRM)
        time.sleep(random.uniform(1.6, 2.2))
        screen = adb_screencap_stable()
        if screen is None or not _find_optional(screen, IMG_TR_EXTRACT_SUCCESS, 0.8)[0]:
            print("[treasure] ไม่เห็น 'Extraction successful' -> หยุด (ไม่แน่ใจผลย่อย)")
            break
        extracted += 1
        adb_tap(*BTN_TR_SUCCESS_CONFIRM)
        time.sleep(random.uniform(1.6, 2.2))
        adb_tap(*BTN_TR_GRID_CLOSE)
        time.sleep(random.uniform(1.6, 2.2))
    print(f"[treasure] จบ — สุ่ม {drawn} / ย่อย {extracted} ชิ้น")


def draw_and_extract_loop(draw_count=None):
    """Run the ROI state machine validated by the Treasure Extract test tool."""
    _require_runtime_license()
    count = int(draw_count if draw_count is not None else SETTINGS.get('treasure_extract_count', 12))
    count = max(1, min(12, count))

    def resolution_ok():
        screen = adb_screencap_stable()
        return screen is not None and screen.shape[:2] == (720, 1280)

    runner = treasure_extract_roi.TreasureExtractRoiRunner(
        serial=ADB_DEVICE or "device",
        draw_count=count,
        stop_event=STOP_FLAG,
        capture_callback=adb_screencap_stable,
        tap_callback=lambda x, y: adb_tap(x, y),
        resolution_callback=resolution_ok,
        log_callback=lambda message: print(f"[treasure] {message}"),
    )
    return runner.run()

def main():
    print('============================================================')
    print(' LDPlayer Game Bot - State Machine')
    print(' กดปุ่ม \'q\' ได้ตลอดเวลาเพื่อหยุดบอท')
    try:
        import keyboard
    except Exception:
        print(' [หมายเหตุ] ไม่พบ library \'keyboard\' -> ปุ่ม q ทำงานเฉพาะเมื่อโฟกัสที่หน้าต่างนี้')
        print('            แนะนำติดตั้ง:  pip install keyboard')
    print('============================================================')
    if not check_connection():
        print('[FATAL] เชื่อมต่อ ADB/แคปหน้าจอไม่ได้ — ตรวจ ADB_DEVICE และคำสั่ง \'adb devices\'')
        return
    watcher = threading.Thread(target=watch_emergency_key, daemon=True)
    watcher.start()
    run_state_machine()

if __name__ == '__main__':
    main()
