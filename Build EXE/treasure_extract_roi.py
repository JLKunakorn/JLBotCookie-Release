import json
import os
import sys
import time
from pathlib import Path

import cv2


RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ROI_ROOT = RESOURCE_ROOT / "treasure_extract_roi"
RULES_FILE = ROI_ROOT / "rules.json"
TEMPLATE_DIR = ROI_ROOT / "templates"

MAX_DRAW_COUNT = 12
CENTER_SKIP = (640, 360)
SELECT_CELLS = [
    (212, 186),
    (351, 184),
    (484, 190),
    (619, 186),
    (206, 331),
    (339, 333),
    (474, 337),
    (615, 327),
    (194, 458),
    (339, 456),
    (484, 454),
    (619, 452),
]

REQUIRED_RULES = {
    "rule1_into_tre",
    "rule2_Draw",
    "rule3_Click",
    "rule4_Cliam",
    "rule5_if_after_rule3_showthis",
    "rule6_if_after_rule3_showthis",
    "rule6.1_Way2",
    "rule8_Extrack",
    "rule9_Sort",
    "rule10_Fav",
    "rule11_selcet",
    "rule12_END",
    "rule14_clear",
    "rule14_clear_confirm",
    "rule14_clear_confirm2",
    "rule20_out",
}


class TreasureExtractRoiRunner:
    def __init__(
        self,
        serial,
        draw_count,
        stop_event,
        capture_callback,
        tap_callback,
        resolution_callback,
        log_callback=print,
    ):
        self.serial = serial
        self.draw_count = max(1, min(MAX_DRAW_COUNT, int(draw_count)))
        self.stop_event = stop_event
        self.capture_callback = capture_callback
        self.tap_callback = tap_callback
        self.resolution_callback = resolution_callback
        self.log_callback = log_callback
        self.rules = self._load_rules()
        self.templates = {}
        self.cycle = 0

    def log(self, message):
        self.log_callback(message)

    def _load_rules(self):
        with RULES_FILE.open("r", encoding="utf-8") as file:
            rules = {rule["name"]: rule for rule in json.load(file)}
        missing = sorted(REQUIRED_RULES.difference(rules))
        if missing:
            raise RuntimeError("ROI rules ไม่ครบ: " + ", ".join(missing))
        return rules

    def _template(self, name):
        if name not in self.templates:
            path = TEMPLATE_DIR / self.rules[name]["template"]
            template = cv2.imread(os.fspath(path), cv2.IMREAD_COLOR)
            if template is None:
                raise FileNotFoundError(f"อ่าน template ไม่ได้: {path}")
            self.templates[name] = template
        return self.templates[name]

    def _capture(self):
        return self.capture_callback()

    def _match(self, screen, name):
        if screen is None:
            return False, 0.0
        rule = self.rules[name]
        template = self._template(name)
        x, y, width, height = (int(value) for value in rule["scan"])
        screen_height, screen_width = screen.shape[:2]
        x1 = max(0, min(screen_width, x))
        y1 = max(0, min(screen_height, y))
        x2 = max(x1, min(screen_width, x + width))
        y2 = max(y1, min(screen_height, y + height))
        roi = screen[y1:y2, x1:x2]
        if roi.size == 0 or roi.shape[0] < template.shape[0] or roi.shape[1] < template.shape[1]:
            return False, 0.0
        result = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, _ = cv2.minMaxLoc(result)
        return float(score) >= float(rule.get("threshold", 0.8)), float(score)

    def _sleep(self, seconds):
        return not self.stop_event.wait(max(0.0, float(seconds)))

    def _tap(self, x, y, wait_after=0.7):
        if self.stop_event.is_set():
            return False
        self.tap_callback(int(x), int(y))
        return self._sleep(wait_after)

    def _tap_rule(self, name, wait_after=1.0):
        tap = self.rules[name].get("tap")
        if not tap:
            raise RuntimeError(f"Rule ไม่มีจุด tap: {name}")
        self.log(f"กด {name} ที่ {tuple(tap)}")
        return self._tap(tap[0], tap[1], wait_after)

    def _wait_for_any(self, names, timeout=15.0, poll=0.3):
        deadline = time.monotonic() + timeout
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            screen = self._capture()
            for name in names:
                found, score = self._match(screen, name)
                if found:
                    self.log(f"พบ {name} score={score:.3f}")
                    return name
            if not self._sleep(poll):
                break
        return None

    def _wait_and_tap(self, name, timeout=15.0, wait_after=1.0):
        found = self._wait_for_any([name], timeout=timeout)
        if not found:
            self.log(f"ไม่พบ {name} ภายใน {timeout:.0f} วินาที")
            return False
        return self._tap_rule(name, wait_after)

    def _wait_until_gone(self, name, timeout=15.0, poll=0.35):
        deadline = time.monotonic() + timeout
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            found, _score = self._match(self._capture(), name)
            if not found:
                self.log(f"{name} หายแล้ว")
                return True
            if not self._sleep(poll):
                break
        self.log(f"{name} ยังไม่หายภายใน {timeout:.0f} วินาที")
        return False

    def _enter_draw_page(self):
        self.log("ตรวจหน้า Treasure Draw (Rule 1 → 2 → 3)")
        deadline = time.monotonic() + 30.0
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            screen = self._capture()
            if self._match(screen, "rule3_Click")[0]:
                return True
            if self._match(screen, "rule2_Draw")[0]:
                self._tap_rule("rule2_Draw", 1.2)
                continue
            if self._match(screen, "rule1_into_tre")[0]:
                self._tap_rule("rule1_into_tre", 1.2)
                continue
            if not self._sleep(0.35):
                break
        self.log("เข้า Treasure Draw ไม่สำเร็จ: ไม่พบ Rule 1/2/3")
        return False

    def _draw_phase(self):
        completed = 0
        while completed < self.draw_count and not self.stop_event.is_set():
            signal_name = self._wait_for_any(
                ["rule5_if_after_rule3_showthis", "rule6_if_after_rule3_showthis", "rule3_Click"],
                timeout=15.0,
            )
            if signal_name in ("rule5_if_after_rule3_showthis", "rule6_if_after_rule3_showthis"):
                return completed, signal_name
            if signal_name != "rule3_Click":
                self.log("รอ Rule 3 หมดเวลา จะเริ่มรอบใหม่")
                return completed, None

            self.log(f"สุ่มสมบัติ {completed + 1}/{self.draw_count}")
            if not self._tap_rule("rule3_Click", 0.8):
                break
            self.log("คลิกกลางจอเพื่อข้ามกล่อง")
            if not self._tap(*CENTER_SKIP, wait_after=0.7):
                break

            outcome = self._wait_for_any(
                ["rule5_if_after_rule3_showthis", "rule6_if_after_rule3_showthis", "rule4_Cliam"],
                timeout=10.0,
            )
            if outcome in ("rule5_if_after_rule3_showthis", "rule6_if_after_rule3_showthis"):
                return completed, outcome
            if outcome != "rule4_Cliam":
                self.log("ไม่พบ Rule 4 หลังเปิดกล่อง จะเริ่มรอบใหม่")
                return completed, None
            if not self._tap_rule("rule4_Cliam", 1.0):
                break
            completed += 1
        return completed, "draw_limit" if completed >= self.draw_count else None

    def _enter_cabinet(self, draw_result):
        if draw_result == "rule5_if_after_rule3_showthis":
            self.log("พบ Rule 5: สมบัติเต็ม (ตรวจอย่างเดียว ไม่กด Rule 5)")
            return self._wait_and_tap("rule6_if_after_rule3_showthis", timeout=20.0, wait_after=1.5)
        if draw_result == "rule6_if_after_rule3_showthis":
            return self._tap_rule("rule6_if_after_rule3_showthis", 1.5)
        if draw_result == "draw_limit":
            self.log("สุ่มครบจำนวนโดยยังไม่พบ Rule 5/6: ใช้ Rule 6.1")
            return self._wait_and_tap("rule6.1_Way2", timeout=15.0, wait_after=1.5)
        return False

    def _prepare_extract(self):
        for name in ("rule8_Extrack", "rule9_Sort", "rule10_Fav"):
            if not self._wait_and_tap(name, timeout=15.0, wait_after=1.0):
                return False
        return bool(self._wait_for_any(["rule11_selcet"], timeout=15.0))

    def _select_treasures(self):
        rule12_seen = False
        for index, (x, y) in enumerate(SELECT_CELLS[:self.draw_count], 1):
            if self.stop_event.is_set():
                return False
            self.log(f"เลือกสมบัติ {index}/{self.draw_count} ที่ ({x}, {y})")
            if not self._tap(x, y, wait_after=0.45):
                return False
            if self._wait_for_any(["rule12_END"], timeout=0.8, poll=0.2):
                self.log("พบ Rule 12: หยุดเลือกทันทีและรอ popup หาย")
                rule12_seen = True
                break
        if rule12_seen and not self._wait_until_gone("rule12_END", timeout=20.0):
            return False
        return True

    def _extract_and_close(self):
        for name in ("rule14_clear", "rule14_clear_confirm", "rule14_clear_confirm2"):
            if not self._wait_and_tap(name, timeout=15.0, wait_after=1.0):
                return False
        return self._wait_and_tap("rule20_out", timeout=15.0, wait_after=1.5)

    def run(self):
        self.log(f"เริ่ม Treasure Extract ROI Test: {self.serial}, จำนวน {self.draw_count}")
        if not self.resolution_callback():
            self.log("หยุด: เครื่องต้องใช้ความละเอียด 1280x720")
            return 1

        while not self.stop_event.is_set():
            self.cycle += 1
            self.log(f"===== รอบใหญ่ {self.cycle} =====")
            if not self._enter_draw_page():
                if not self._sleep(1.0):
                    break
                continue
            completed, draw_result = self._draw_phase()
            self.log(f"จบช่วงสุ่ม: สำเร็จ {completed}/{self.draw_count}, result={draw_result}")
            if not self._enter_cabinet(draw_result):
                if not self._sleep(1.0):
                    break
                continue
            if not self._prepare_extract():
                if not self._sleep(1.0):
                    break
                continue
            if not self._select_treasures():
                if not self._sleep(1.0):
                    break
                continue
            if not self._extract_and_close():
                if not self._sleep(1.0):
                    break
                continue
            self.log("ย่อยและปิดสำเร็จ กลับไปเริ่ม Rule 3 รอบถัดไป")

        self.log("ยกเลิก Treasure Extract ROI Test แล้ว")
        return 0

