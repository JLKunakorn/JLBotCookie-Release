from __future__ import annotations

from dataclasses import dataclass, field
import os
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np


DIGIT_SIZE = (24, 36)
DEFAULT_DIGIT_DIR = os.path.join("templates", "dig")

PROFILE_COIN_RESULT = "coin_result"
PROFILE_MAIL_BADGE = "mail_badge"
PROFILE_TREASURE_POWDER = "treasure_powder"

PROFILES = {
    PROFILE_COIN_RESULT: {
        "mode": "threshold_inv",
        "threshold": 110,
        "min_score": 0.3,
        "min_height": 8,
        "min_width": 3,
        "min_height_ratio": 0.55,
        "split_touching": True,
    },
    PROFILE_TREASURE_POWDER: {
        "mode": "threshold_inv",
        "threshold": 90,
        "min_score": 0.3,
        "min_height": 12,
        "min_width": 4,
        "min_height_ratio": 0.55,
        "split_touching": True,
    },
    PROFILE_MAIL_BADGE: {
        "mode": "mail_badge",
        "min_score": 0.3,
        "min_height": 8,
        "min_width": 3,
        "min_height_ratio": 0.45,
        "split_touching": True,
    },
}

_DIGIT_TEMPLATES: Optional[Dict[str, np.ndarray]] = None


@dataclass(frozen=True)
class OcrResult:
    value: Optional[int]
    confidence: float = 0.0
    raw_digits: str = ""
    digit_scores: Tuple[float, ...] = field(default_factory=tuple)
    profile: str = ""
    reason: str = ""


def _resource_root() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _digit_dir(path: Optional[str] = None) -> str:
    return path or os.path.join(_resource_root(), DEFAULT_DIGIT_DIR)


def clear_template_cache() -> None:
    global _DIGIT_TEMPLATES
    _DIGIT_TEMPLATES = None


def load_digit_templates(path: Optional[str] = None) -> Dict[str, np.ndarray]:
    global _DIGIT_TEMPLATES
    if _DIGIT_TEMPLATES is not None and path is None:
        return _DIGIT_TEMPLATES

    templates = {}
    root = _digit_dir(path)
    for digit in "0123456789":
        image = cv2.imread(os.path.join(root, f"{digit}.png"), cv2.IMREAD_GRAYSCALE)
        if image is None:
            continue
        if image.shape != (DIGIT_SIZE[1], DIGIT_SIZE[0]):
            image = cv2.resize(image, DIGIT_SIZE)
        templates[digit] = image.astype(np.float32)

    if path is None:
        _DIGIT_TEMPLATES = templates
    return templates


def _profile(profile: str) -> Dict[str, object]:
    if profile not in PROFILES:
        raise ValueError(f"unknown OCR profile: {profile}")
    return PROFILES[profile]


def _ensure_bgr(crop: np.ndarray) -> np.ndarray:
    if crop.ndim == 2:
        return cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    return crop


def _threshold_inv(crop: np.ndarray, threshold: int) -> np.ndarray:
    bgr = _ensure_bgr(crop)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, int(threshold), 255, cv2.THRESH_BINARY_INV)
    return mask


def _mail_badge_mask(crop: np.ndarray) -> np.ndarray:
    bgr = _ensure_bgr(crop)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 120, 120), (10, 255, 255)) | cv2.inRange(hsv, (170, 120, 120), (180, 255, 255))
    contours, _ = cv2.findContours(red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 80:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if h < 10 or h > 56 or w < 10:
            continue
        if best is None or area > best[0]:
            best = (area, x, y, w, h)

    if best is not None:
        _, x, y, w, h = best
        pad = 3
        roi = bgr[y + pad:y + h - pad, x + pad:x + w - pad]
    else:
        roi = bgr

    if roi.size == 0:
        return np.zeros((0, 0), dtype=np.uint8)

    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv_roi, (0, 0, 185), (180, 90, 255))


def preprocess_digits(crop: np.ndarray, profile: str) -> np.ndarray:
    cfg = _profile(profile)
    if crop is None or crop.size == 0:
        return np.zeros((0, 0), dtype=np.uint8)
    if cfg["mode"] == "mail_badge":
        return _mail_badge_mask(crop)
    return _threshold_inv(crop, int(cfg["threshold"]))


def _split_wide_box(box: Sequence[int]) -> List[List[int]]:
    x0, y0, x1, y1 = [int(v) for v in box]
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    expected_width = max(1.0, height * DIGIT_SIZE[0] / DIGIT_SIZE[1])
    parts = int(round(width / expected_width))
    if parts <= 1 or width < expected_width * 1.35:
        return [[x0, y0, x1, y1]]
    parts = max(1, min(parts, 6))
    out = []
    for index in range(parts):
        sx0 = x0 + int(round(width * index / parts))
        sx1 = x0 + int(round(width * (index + 1) / parts))
        if sx1 > sx0:
            out.append([sx0, y0, sx1, y1])
    return out or [[x0, y0, x1, y1]]


def segment_digits(mask: np.ndarray, profile: str = PROFILE_COIN_RESULT) -> List[List[int]]:
    cfg = _profile(profile)
    if mask is None or mask.size == 0:
        return []

    cols = mask.sum(axis=0)
    groups = []
    in_run = False
    start = 0
    for x, value in enumerate(cols):
        if value > 0 and not in_run:
            start = x
            in_run = True
        elif value == 0 and in_run:
            groups.append((start, x))
            in_run = False
    if in_run:
        groups.append((start, len(cols)))

    boxes = []
    for x0, x1 in groups:
        rows = np.where(mask[:, x0:x1].sum(axis=1) > 0)[0]
        if not len(rows):
            continue
        y0, y1 = int(rows[0]), int(rows[-1] + 1)
        if y1 - y0 < int(cfg["min_height"]) or x1 - x0 < int(cfg["min_width"]):
            continue
        boxes.append([int(x0), y0, int(x1), y1])

    if not boxes:
        return []

    max_height = max(box[3] - box[1] for box in boxes)
    boxes = [box for box in boxes if box[3] - box[1] >= float(cfg["min_height_ratio"]) * max_height]

    split = []
    for box in boxes:
        split.extend(_split_wide_box(box) if cfg.get("split_touching") else [box])
    return sorted(split, key=lambda b: b[0])


def _match_digit(mask: np.ndarray, box: Sequence[int], templates: Dict[str, np.ndarray]) -> Tuple[str, float]:
    x0, y0, x1, y1 = [int(v) for v in box]
    glyph = mask[y0:y1, x0:x1]
    if glyph.size == 0:
        return "", -1.0
    glyph = cv2.resize(glyph, DIGIT_SIZE).astype(np.float32)
    best_digit = ""
    best_score = -1.0
    for digit, template in templates.items():
        score = float(cv2.matchTemplate(glyph, template, cv2.TM_CCOEFF_NORMED)[0][0])
        if score > best_score:
            best_digit = digit
            best_score = score
    return best_digit, best_score


def read_digits(crop: np.ndarray, profile: str = PROFILE_COIN_RESULT, min_score: Optional[float] = None,
                template_dir: Optional[str] = None) -> OcrResult:
    cfg = _profile(profile)
    templates = load_digit_templates(template_dir)
    if len(templates) < 10:
        return OcrResult(None, profile=profile, reason="missing_templates")

    mask = preprocess_digits(crop, profile)
    boxes = segment_digits(mask, profile)
    if not boxes:
        return OcrResult(None, profile=profile, reason="no_digits")

    threshold = float(cfg["min_score"] if min_score is None else min_score)
    digits = []
    scores = []
    for box in boxes:
        digit, score = _match_digit(mask, box, templates)
        if not digit or score < threshold:
            raw = "".join(digits)
            return OcrResult(None, max(scores or [0.0]), raw, tuple(scores), profile, "low_confidence")
        digits.append(digit)
        scores.append(score)

    raw = "".join(digits)
    try:
        value = int(raw)
    except ValueError:
        return OcrResult(None, max(scores or [0.0]), raw, tuple(scores), profile, "invalid_digits")
    return OcrResult(value, min(scores), raw, tuple(scores), profile, "")


def read_roi(screen: np.ndarray, roi: Sequence[int], profile: str, min_score: Optional[float] = None) -> OcrResult:
    if screen is None or len(roi) != 4:
        return OcrResult(None, profile=profile, reason="invalid_roi")
    x1, y1, x2, y2 = [int(v) for v in roi]
    h, w = screen.shape[:2]
    x1, x2 = max(0, x1), min(w, x2)
    y1, y2 = max(0, y1), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return OcrResult(None, profile=profile, reason="invalid_roi")
    return read_digits(screen[y1:y2, x1:x2], profile=profile, min_score=min_score)


def read_coin_result(screen: np.ndarray, roi: Sequence[int] = (945, 383, 1118, 430)) -> OcrResult:
    return read_roi(screen, roi, PROFILE_COIN_RESULT)


def read_treasure_powder(screen: np.ndarray, roi: Sequence[int] = (1035, 583, 1150, 620)) -> OcrResult:
    return read_roi(screen, roi, PROFILE_TREASURE_POWDER)


def read_mail_badge_crop(crop: np.ndarray) -> OcrResult:
    return read_digits(crop, PROFILE_MAIL_BADGE)


def values(results: Iterable[OcrResult]) -> List[Optional[int]]:
    return [result.value for result in results]
