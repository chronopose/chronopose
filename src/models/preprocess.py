"""Skeleton Preprocessor (SCRUM-39): буфер скелетов по трекам, маска пропусков, окна 2 с, признаки.

Признаки считаются в «длинах туловища» (плечи → бёдра), поэтому не зависят от того,
далеко человек от камеры или близко.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

from src.contracts import PersonPose

MIN_CONF = 0.3
L_SH, R_SH, L_HIP, R_HIP = 5, 6, 11, 12
FEATURES = ["angle_end", "angle_change", "angle_std", "drop", "vdown", "speed_x", "aspect_end", "coverage"]


@dataclass
class Frame:
    t: float
    kps: np.ndarray        # 17×3: x, y, уверенность; пропуски — NaN в x, y
    bbox: Tuple[float, float, float, float]


def mask_missing(kps: List[Tuple[float, float, float]], min_conf: float = MIN_CONF) -> np.ndarray:
    a = np.asarray(kps, dtype=float).reshape(17, 3)
    a[a[:, 2] < min_conf, :2] = np.nan
    return a


def _mid(a: np.ndarray, i: int, j: int) -> np.ndarray:
    pts = a[[i, j], :2]
    return np.nanmean(pts, axis=0) if not np.all(np.isnan(pts)) else np.array([np.nan, np.nan])


def normalize(kps: np.ndarray) -> np.ndarray:
    """Центр — середина бёдер, масштаб — длина туловища. Для ML-моделей на сырых скелетах."""
    hip, sh = _mid(kps, L_HIP, R_HIP), _mid(kps, L_SH, R_SH)
    scale = float(np.linalg.norm(sh - hip)) if not np.any(np.isnan(sh - hip)) else np.nan
    out = kps.copy()
    if np.isnan(scale) or scale < 1e-6:
        out[:, :2] = np.nan
        return out
    out[:, :2] = (kps[:, :2] - hip) / scale
    return out


class SkeletonBuffer:
    """Последние секунды скелетов одного трека."""

    def __init__(self, keep_s: float = 4.0) -> None:
        self.keep_s = keep_s
        self.frames: Deque[Frame] = deque()

    def add(self, t: float, p: PersonPose) -> None:
        self.frames.append(Frame(t, mask_missing(p.keypoints), p.bbox))
        while self.frames and t - self.frames[0].t > self.keep_s:
            self.frames.popleft()

    def window(self, t_end: float, length: float = 2.0) -> List[Frame]:
        return [f for f in self.frames if t_end - length <= f.t <= t_end]


def features(window: List[Frame], length: float = 2.0) -> Optional[Dict[str, float]]:
    """Признаки окна. None — данных мало (меньше трети окна с видимым туловищем)."""
    rows = []
    for f in window:
        sh, hip = _mid(f.kps, L_SH, R_SH), _mid(f.kps, L_HIP, R_HIP)
        if np.any(np.isnan(sh)) or np.any(np.isnan(hip)):
            continue
        v = sh - hip
        angle = math.degrees(math.atan2(abs(v[0]), -v[1]))  # 0 — вертикально, 90 — лёжа
        rows.append((f.t, angle, float(np.linalg.norm(v)), sh[1], hip[0], f.bbox))
    if len(rows) < 3:
        return None
    t = np.array([r[0] for r in rows])
    ang = np.array([r[1] for r in rows])
    torso = float(np.median([r[2] for r in rows])) or 1.0
    sh_y = np.array([r[3] for r in rows])
    hip_x = np.array([r[4] for r in rows])
    dt = np.diff(t)
    dt[dt <= 0] = 1e-3
    vdown = float(np.max(np.diff(sh_y) / dt) / torso) if len(rows) > 1 else 0.0
    first = ang[: max(1, len(ang) // 2)]
    x1, y1, x2, y2 = rows[-1][5]
    span = max(t[-1] - t[0], 1e-3)
    return {
        "angle_end": float(np.mean(ang[-3:])),
        "angle_change": float(np.mean(ang[-3:]) - np.min(first)),
        "angle_std": float(np.std(ang)),
        "drop": float((np.mean(sh_y[-3:]) - np.min(sh_y)) / torso),
        "vdown": max(0.0, vdown),
        "speed_x": float(abs(hip_x[-1] - hip_x[0]) / span / torso),
        "aspect_end": float((x2 - x1) / max(y2 - y1, 1e-3)),
        "coverage": float(min(1.0, span / length)),
    }


def feature_vector(f: Dict[str, float]) -> List[float]:
    return [f[k] for k in FEATURES]
