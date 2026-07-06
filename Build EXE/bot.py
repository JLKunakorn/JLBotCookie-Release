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
            cands.append(os.path.join(base, 'MuMu', 'emulator', 'nemu', 'vmonitor', 'bin', 'adb_server.exe'))
    for c in cands:
        if os.path.exists(c):
            return c
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

def list_emu_instances(emu):
    """Connect likely ports for one emulator brand and return online serials."""
    profile = EMU_PROFILES.get(emu)
    adb_path = adb_path_for_emu(emu)
    ports = list(profile['ports']) if profile else list(EMU_CONNECT_PORTS)
    def _try(port):
        try:
            if _port_open(port):
                _run([adb_path, 'connect', '127.0.0.1:%d' % port], timeout=4)
        except Exception:
            return None
    threads = [threading.Thread(target=_try, args=(p,), daemon=True) for p in ports]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    return _list_online_devices_with_adb(adb_path)

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
REQUIRED_BOT_TIER = "pro"

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
        return True
    ok, info = license_core.check_license(force_online=False)
    if not ok:
        clear_license_context()
        raise RuntimeError(f'license ไม่ผ่าน: {info}')
    tier = str(info.get('tier') or '').strip().lower() if isinstance(info, dict) else ''
    if REQUIRED_BOT_TIER and tier != REQUIRED_BOT_TIER:
        clear_license_context()
        raise RuntimeError(f'license tier ไม่ถูกต้อง: {tier or "ไม่มี tier"}')
    set_license_context(info)
    return True

# --- GLOBAL STATES ---
ADB_PATH = find_adb()
ADB_DEVICE = None if MULTI_EMU else 'emulator-5554'
BOT_VERSION = '3.6'
PREVENT_INACTIVE = BOT_VERSION == '2.1'
BOT_TIER = 'pro'

# --- TEMPLATES & THRESHOLDS ---
MATCH_THRESHOLD = 0.85
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
    'use_relay': True, 
    'use_multibuy': True, 
    'boost_potion': True, 
    'boost_stopwatch': True, 
    'boost_star': True, 
    'avoid_revive': True, 
    'use_faststart': False,
    'use_relic': True,
    'use_mail_lives': False
}

# --- SCREEN & COORDINATES ---
IMG_FASTSTART = 'templates/faststart_prompt.png'
BTN_FASTSTART = (655, 345)
FASTSTART_THRESHOLD = 0.9
FASTSTART_WINDOW = 25.0
IMG_PITLIFT = 'templates/pitlift_popup.png'
PITLIFT_THRESHOLD = 0.8
BTN_PITLIFT_NO = None
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

# --- MAILBOX CONFIGS ---
BTN_MAILBOX = (688, 675)
BTN_MAIL_LIVES = (632, 145)
BTN_MAIL_QUICK = (637, 610)
BTN_MAIL_CONFIRM = (793, 458)
BTN_MAIL_DONE = (640, 458)
BTN_MAIL_CLOSE = (1129, 88)
IMG_MAILBOX = 'templates/mailbox_title.png'
IMG_MAILICON = 'templates/mail_icon.png'
MAIL_MIN_COUNT = 0
MAIL_CONFIRM_MAX = 320
MAIL_PROGRESS_BOX = (400, 255, 880, 320)
MAIL_PROGRESS_MIN = 6.0
MAIL_BADGE_OFFSET = (10, -52, 72, -8)
MAIL_ICON_THRESHOLD = 0.85

# --- RELIC CONFIGS ---
IMG_RELIC_GET = 'templates/relic_get.png'
IMG_RELIC_TITLE = 'templates/relic_title.png'
RELIC_GET_POS = (530, 83)
BTN_RELIC_OPEN = (515, 100)
BTN_RELIC_BTN = (640, 576)
BTN_RELIC_CLOSE = (1077, 155)
RELIC_TAP_MAX = 8

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
RESULT_CHECK_INTERVAL = 0.5
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

def adb_screencap():
    cmd = _adb_base() + ['exec-out', 'screencap', '-p']
    try:
        result = _run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        if not result.stdout:
            print('[ERR] แคปหน้าจอไม่ได้:', result.stderr.decode(errors='ignore'))
            return None
        img_array = np.frombuffer(result.stdout, dtype=np.uint8)
        screen = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return screen
    except subprocess.TimeoutExpired:
        print('[ERR] ADB screencap timeout')
        return None
    except Exception as e:
        print(f'[ERR] adb_screencap: {e}')
        return None

def adb_tap(x, y, jitter=None):
    j = TAP_JITTER if jitter is None else jitter
    if j and j > 0:
        x = min(1279, max(0, int(x) + random.randint(-j, j)))
        y = min(719, max(0, int(y) + random.randint(-j, j)))
    _run(_adb_base() + ['shell', 'input', 'tap', str(int(x)), str(int(y))])

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
    adb_hold(x, y, SLIDE_HOLD_SEC)

def _jump_point():
    x1, y1, x2, y2 = JUMP_ZONE
    return (random.randint(x1, x2), random.randint(y1, y2))

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

def read_mail_badge(screen):
    if screen is None:
        return None
    tpls = _load_digit_templates()
    if not tpls:
        return None
    mf, mp, _ = _find_optional(screen, IMG_MAILICON, MAIL_ICON_THRESHOLD)
    if not mf:
        return None
    dx1, dy1, dx2, dy2 = MAIL_BADGE_OFFSET
    x0, y0 = (mp[0] + dx1, mp[1] + dy1)
    x1, y1 = (mp[0] + dx2, mp[1] + dy2)
    h_img, w_img = screen.shape[:2]
    x0, y0 = (max(0, x0), max(0, y0))
    x1, y1 = (min(w_img, x1), min(h_img, y1))
    if x1 <= x0 or y1 <= y0:
        return None
    zone = screen[y0:y1, x0:x1]
    hsv = cv2.cvtColor(zone, cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 120, 120), (10, 255, 255)) | cv2.inRange(hsv, (170, 120, 120), (180, 255, 255))
    cnts, _ = cv2.findContours(red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in cnts:
        a = cv2.contourArea(c)
        if a < 150:
            continue
        bx, by, bw, bh = cv2.boundingRect(c)
        if bh < 14 or bh > 34:
            continue
        if bw < 16 or bw > 55:
            continue
        if best is None or a > best[0]:
            best = (a, bx, by, bw, bh)
    if not best:
        return None
    _, bx, by, bw, bh = best
    pad = 3
    pill = zone[by + pad:by + bh - pad, bx + pad:bx + bw - pad]
    if pill.size == 0:
        return None
    phsv = cv2.cvtColor(pill, cv2.COLOR_BGR2HSV)
    white = cv2.inRange(phsv, (0, 0, 185), (180, 90, 255))
    cols = white.sum(axis=0)
    groups, inrun, st = ([], False, 0)
    for i, v in enumerate(cols):
        if v > 0 and (not inrun):
            st, inrun = (i, True)
        elif v == 0 and inrun:
            groups.append((st, i))
            inrun = False
    if inrun:
        groups.append((st, len(cols)))
    digits = ''
    for a0, a1 in groups:
        rows = np.where(white[:, a0:a1].sum(axis=1) > 0)[0]
        if not len(rows):
            continue
        g = white[rows[0]:rows[-1] + 1, a0:a1]
        if g.shape[0] < 8 or g.shape[1] < 3:
            continue
        g = cv2.resize(g, (_DIG_GW, _DIG_GH)).astype(np.float32)
        scores = {d: cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)[0][0] for d, t in tpls.items()}
        digits += max(scores, key=scores.get)
    try:
        return int(digits) if digits else None
    except ValueError:
        return None

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

def collect_relic():
    _require_runtime_license()
    print('[โบราณวัตถุ] ตรวจพบรางวัลพร้อมรับ! -> กำลังเข้าไปรับรางวัล Relic')
    adb_tap(*BTN_RELIC_OPEN)
    time.sleep(random.uniform(1.8, 2.6))
    screen = adb_screencap()
    rf, _, rsc = _find_optional(screen, IMG_RELIC_TITLE, 0.85)
    if not rf:
        print(f'[โบราณวัตถุ] เปิดหน้าต่างวัตถุโบราณไม่สำเร็จ (ความมั่นใจ={rsc:.2f}) -> ข้ามรอบนี้')
        return False
    taps = 0
    misses = 0
    for _ in range(RELIC_TAP_MAX * 2):
        if STOP_FLAG.is_set():
            break
        screen = adb_screencap()
        if _btn_green_ratio(screen, *BTN_RELIC_BTN, half=34) > 0.5:
            adb_tap(*BTN_RELIC_BTN)
            taps += 1
            misses = 0
            if taps >= RELIC_TAP_MAX:
                print('[โบราณวัตถุ] กดรับรางวัลเกินกำหนดสูงสุด -> ปิดหน้าต่างวัตถุโบราณ')
                break
            time.sleep(random.uniform(1.0, 1.7))
            continue
        misses += 1
        if misses >= (3 if taps == 0 else 4):
            break
        time.sleep(random.uniform(0.9, 1.4))
    print(f'[โบราณวัตถุ] ดำเนินการรับรางวัลเรียบร้อย (กดไปทั้งหมด {taps} ครั้ง) -> กลับล็อบบี้')
    adb_tap(*BTN_RELIC_CLOSE)
    time.sleep(random.uniform(1.2, 1.8))
    _escape_to_lobby()
    return True

def maybe_collect_relic(screen=None):
    if not SETTINGS.get('use_relic', False):
        return None
    if screen is None:
        screen = adb_screencap()
    lf, lp, _ = find_template(screen, IMG_LOBBY_PLAY)
    if not lf or _play_is_dim(screen, lp):
        return None
    gf, gp, _ = _find_optional(screen, IMG_RELIC_GET, 0.85)
    if not gf:
        return None
    if abs(gp[0] - RELIC_GET_POS[0]) > 40 or abs(gp[1] - RELIC_GET_POS[1]) > 40:
        return None
    return collect_relic()

def collect_mail_lives():
    _require_runtime_license()
    screen = adb_screencap()
    lf, _, _ = find_template(screen, IMG_LOBBY_PLAY)
    if not lf:
        print('[ระบบจดหมาย] ตรวจไม่พบหน้าล็อบบี้ -> ข้ามการเก็บหัวใจชั่วคราว')
        return False
    print('[ระบบจดหมาย] ตรวจสอบพบจดหมายใหม่ -> เข้าสู่กล่องจดหมายเพื่อรับและส่งหัวใจด่วน')
    adb_tap(*BTN_MAILBOX)
    time.sleep(random.uniform(1.5, 2.2))
    screen = adb_screencap()
    mf, _, msc = _find_optional(screen, IMG_MAILBOX, 0.8)
    if not mf:
        print(f'[ระบบจดหมาย] เปิดกล่องจดหมายไม่สำเร็จ (ความมั่นใจ={msc:.2f}) -> ข้ามรอบนี้')
        return False
    adb_tap(*BTN_MAIL_LIVES)
    time.sleep(random.uniform(0.7, 1.2))
    adb_tap(*BTN_MAIL_QUICK)
    time.sleep(random.uniform(1.0, 1.6))
    got = 0
    stuck = 0
    last_reg = None
    for _ in range(MAIL_CONFIRM_MAX):
        if STOP_FLAG.is_set():
            break
        screen = adb_screencap()
        reg = _region_gray(screen, MAIL_PROGRESS_BOX)
        if reg is not None and last_reg is not None and (reg.shape == last_reg.shape) and (float(np.mean(np.abs(reg - last_reg))) < MAIL_PROGRESS_MIN):
            stuck += 1
            if stuck >= 4:
                print('[ระบบจดหมาย] ข้อมูลการกดไม่ตอบสนอง -> ปิดกล่องจดหมายเพื่อป้องกันข้อผิดพลาด')
                break
        else:
            stuck = 0
        last_reg = reg
        if _btn_green_ratio(screen, *BTN_MAIL_CONFIRM) > 0.5:
            adb_tap(*BTN_MAIL_CONFIRM)
            got += 1
            time.sleep(random.uniform(0.8, 1.5))
            continue
        if _btn_green_ratio(screen, *BTN_MAIL_DONE) > 0.5:
            print(f'[ระบบจดหมาย] ดำเนินการรับและส่งหัวใจสำเร็จ (กดยืนยันไป {got} รายชื่อ)')
            adb_tap(*BTN_MAIL_DONE)
            time.sleep(random.uniform(0.8, 1.4))
            break
        if got == 0:
            print('[ระบบจดหมาย] ไม่มีจดหมายหัวใจให้รับในเมลตอนนี้')
        break
    adb_tap(*BTN_MAIL_CLOSE)
    time.sleep(random.uniform(1.2, 1.8))
    _escape_to_lobby()
    return True

def maybe_collect_mail_lives(screen=None):
    if not SETTINGS.get('use_mail_lives', False):
        return False
    if MAIL_MIN_COUNT <= 0:
        return False
    if screen is None:
        screen = adb_screencap()
    lf, lp, _ = find_template(screen, IMG_LOBBY_PLAY)
    if not lf or _play_is_dim(screen, lp):
        return False
    n = read_mail_badge(screen)
    if n is None:
        return False
    if n >= MAIL_MIN_COUNT:
        print(f'[ระบบจดหมาย] มีจดหมายใหม่ค้างอยู่ {n} ฉบับ (ถึงเกณฑ์ขั้นต่ำ {MAIL_MIN_COUNT} ฉบับ) -> เริ่มเก็บหัวใจ')
        return collect_mail_lives()
    print(f'[ระบบจดหมาย] มีจดหมายค้าง {n} ฉบับ (ยังไม่ถึงเกณฑ์ {MAIL_MIN_COUNT} ฉบับ) -> ดำเนินการวิ่งต่อ')
    return False

def _lobby_side_tasks(screen):
    if maybe_collect_mail_lives(screen):
        return True
    return False

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
        else:
            if _find_optional(screen, IMG_MAILBOX, 0.8)[0]:
                print('[ระบบนำทาง] ปิด Mailbox เพื่อกลับล็อบบี้')
                adb_tap(*BTN_MAIL_CLOSE)
                acted = True
            elif _find_optional(screen, IMG_RELIC_TITLE, 0.85)[0]:
                print('[ระบบนำทาง] ปิด Relic เพื่อกลับล็อบบี้')
                adb_tap(*BTN_RELIC_CLOSE)
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
        time.sleep(0.9)
        return True
    if allow_fallback:
        for fx, fy in GENERIC_CLOSE_FALLBACK:
            print(f'[ระบบนำทาง] หน้าจอไม่ตอบสนองชั่วคราว -> พยายามกดตำแหน่งฉุกเฉิน ({fx},{fy})')
            adb_tap(fx, fy)
            time.sleep(0.6)
        return True
    return False

def ensure_on_boost_screen(max_tries=15):
    x_close_tries = 0
    side_budget = 2
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
                    time.sleep(0.9)
                else:
                    print(f"[ระบบนำทาง] ไม่สามารถปิดหน้าต่าง {pop['name']} ได้หลังลองหลายครั้ง -> ยุติเพื่อความปลอดภัย")
                    time.sleep(0.8)
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
                    time.sleep(1.2)
                    continue
            dismissed_confirm = False
            for cp in CONFIRM_POPUPS:
                cf, _, csc = find_template(screen, cp['img'], cp['th'])
                if cf:
                    print(f"[ระบบนำทาง] ตรวจพบหน้าต่าง {cp['name']} -> กดยืนยันป๊อปอัปที่พิกัด {cp['btn']}")
                    adb_tap(*cp['btn'])
                    time.sleep(1.2)
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
                time.sleep(2.5)
            else:
                if lf:
                    if side_budget > 0 and _lobby_side_tasks(screen):
                        side_budget -= 1
                        continue
                    print(f'[ระบบนำทาง] หน้าจอหลักเรียบร้อยดี (ครั้งที่ {i + 1}) -> กดเริ่มเกมเพื่อเข้าหน้าเตรียมวิ่ง')
                    adb_tap(*lp)
                    time.sleep(DELAY_AFTER_PLAY)
                else:
                    if not dismiss_unknown_popup(screen):
                        gpos = _find_green_confirm(screen)
                        if gpos:
                            print(f'[ระบบนำทาง] ตรวจพบปุ่มสีเขียวยืนยันกลางหน้าจอที่พิกัด {gpos} -> กดเคลียร์หน้าจอ')
                            adb_tap(*gpos)
                            time.sleep(1.2)
                        else:
                            print(f'[ระบบนำทาง] มีหน้าต่างอื่นบดบังอยู่ -> พยายามกดยืนยันจุดเคลียร์หน้าจอ 2 จุด')
                            adb_tap(*BTN_POPUP_CONFIRM)
                            time.sleep(0.4)
                            adb_tap(*BTN_POPUP_CONFIRM_LOW)
                            time.sleep(1.2)
                            if i >= max_tries - 3:
                                dismiss_unknown_popup(screen, allow_fallback=True)
    print('[ระบบนำทาง] ⚠️ ไม่สามารถเข้าสู่หน้าเตรียมตัวได้ในเวลาที่กำหนด')
    return False

def multibuy_until_target():
    print('[reroll] เลือกกล่อง Random Boost ก่อน')
    adb_tap(*BTN_BOX)
    time.sleep(0.8)
    print('[reroll] เปิดหน้า Multi (เลือกบูสต์ที่ต้องการ)')
    adb_tap(*BTN_MULTI)
    time.sleep(1.0)
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
        time.sleep(0.4)
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
            time.sleep(0.8)
            return True
        if find_template(screen, IMG_TARGET_ITEM)[0]:
            print('[reroll] ได้ Double Coins แล้ว')
            return True
        if time.time() - start > 4.0 and find_template(screen, IMG_BOOST_SCREEN)[0]:
            print('[reroll] ไม่พบการสุ่ม (อาจเหรียญไม่พอ/จบทันที) -> ไปต่อ')
            return True
    print('[reroll] หมดเวลา Multi-Buy -> ปิดหน้า Multi')
    adb_tap(*BTN_MULTI_CLOSE)
    time.sleep(1.0)
    return False

# --- STATE MACHINE CONTROLS ---

def state_reroll():
    print('\n===== [STATE 1] REROLL — Multi-Buy สุ่มบูสต์ที่เลือก =====')
    if not ensure_on_boost_screen():
        print('[WARN] นำทางยังไม่สำเร็จ -> รอแล้ววนลองใหม่ (ไม่หยุดบอท)')
        time.sleep(3)
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
    time.sleep(DELAY_AFTER_PLAY)
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
    pattern = REPLAY_PATTERN
    jump_stop = threading.Event()
    jump_count = [0]
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
                if action == 'slide':
                    threading.Thread(target=adb_slide, daemon=True).start()
                else:
                    adb_tap(*BTN_JUMP, jitter=JUMP_JITTER)
                jump_count[0] += 1
            print(f'[replay] เล่นซ้ำ pattern ครบ {jump_count[0]} การกดแล้ว (รอจบรอบ)')
    else:
        if SETTINGS.get('use_jump', True):
            print('\n===== [STATE 2] RUN — กด Jump สุ่มตำแหน่งโซน 2 มิติ+ดีเลย์ + คอยกด relay =====')
            def worker_loop():
                while not jump_stop.is_set() and (not STOP_FLAG.is_set()):
                    adb_tap(*_jump_point(), jitter=0)
                    jump_count[0] += 1
                    time.sleep(random.uniform(JUMP_DELAY_MIN, JUMP_DELAY_MAX))
        else:
            print('\n===== [STATE 2] RUN — โหมดกดสุ่มห่างๆ (กระโดด/สไลด์ นานๆที) + คอยกด relay =====')
            def worker_loop():
                while not jump_stop.is_set() and (not STOP_FLAG.is_set()):
                    end = time.time() + random.uniform(IDLE_ACTION_MIN, IDLE_ACTION_MAX)
                    while time.time() < end:
                        if jump_stop.is_set() or STOP_FLAG.is_set():
                            return None
                        time.sleep(min(0.2, max(0.0, end - time.time())))
                    if random.random() < IDLE_SLIDE_CHANCE:
                        threading.Thread(target=adb_slide, daemon=True).start()
                    else:
                        adb_tap(*_jump_point(), jitter=0)
                    jump_count[0] += 1

    start_time = time.time()
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
                        time.sleep(1.2)
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
                    time.sleep(0.5)
                    continue
            found_relay, rpos, rscore = find_template(screen, IMG_RELAY, RELAY_THRESHOLD)
            if found_relay:
                if SETTINGS['use_relay']:
                    print(f'    [relay] เจอนินจา (score={rscore:.3f}) -> กดวิ่งต่อ')
                    adb_tap(*BTN_RELAY)
                    time.sleep(0.5)
                    continue
                else:
                    print(f'    [relay] เจอนินจา (score={rscore:.3f}) แต่ปิดใช้นินจาไว้ -> ปล่อยจบรอบ')
            found_result, _, sscore = find_template(screen, IMG_RESULT)
            if found_result:
                print(f'[OK] เจอหน้า Result (score={sscore:.3f}) หลังกด Jump {jump_count[0]} ครั้ง -> STATE 3')
                return State.RESULT
            if t >= RUN_STATE_TIMEOUT:
                print(f'[WARN] State 2 เกินเวลา {RUN_STATE_TIMEOUT}s -> บังคับไป STATE 3')
                return State.RESULT
            time.sleep(RESULT_CHECK_INTERVAL)
    finally:
        jump_stop.set()

COIN_LOG_ROI = (945, 383, 1118, 430)
COIN_TOTAL = 0
COIN_CALLBACK = None

def _writable_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

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
        log_dir = os.path.join(_writable_dir(), 'coin_logs')
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        with open(os.path.join(log_dir, 'coins.csv'), 'a', encoding='utf-8') as f:
            f.write(f"{ts},{(coins if coins is not None else '')},{COIN_TOTAL}\n")
        if coins is not None:
            print(f'[coins] เหรียญรอบนี้: {coins:,}  (รวม {COIN_TOTAL:,})')
        else:
            cv2.imwrite(os.path.join(log_dir, f'result_FAIL_{ts}.png'), screen)
            print(f'[coins] อ่านเลขเหรียญไม่ได้ -> เซฟภาพไว้ result_FAIL_{ts}.png')
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
            time.sleep(1.5)
            print(f'[OK] เจอปุ่ม OK (score={score:.3f}) -> กดกลับล็อบบี้')
            adb_tap(*pos)
            time.sleep(2.5)
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
                print(traceback.format_exc())
                if err_streak >= 30:
                    print('[FATAL] ผิดพลาดติดกันเยอะมาก -> หยุด (เช็ก LDPlayer/ADB ว่ายังเปิดอยู่ไหม)')
                    break
                time.sleep(1.5)
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
