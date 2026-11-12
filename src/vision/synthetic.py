"""Синтетическая сцена: люди идут, один падает и лежит. Без камеры и без нейросети.

Нужна для трёх вещей: сквозной тест в CI, демо без железа (`--synthetic`) и отладка
классификатора. Скелет — та же модель ходьбы, что в анимациях презентации.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from src.contracts import Observation, PersonPose

FEET_Y = 0.84  # ступни ниже бедра на 0,84 «единицы тела»


def walk_pose(phase: float) -> List[List[float]]:
    """17 точек COCO в единицах тела, бедро в (0, 0), ось y вниз."""
    p: List[List[float]] = [[0.0, 0.0] for _ in range(17)]
    bob = -0.022 * abs(math.sin(phase))
    sh = [0.03, -0.52 + bob]

    def leg(ph: float, dx: float):
        th = 0.48 * math.sin(ph)
        fl = 0.12 + 0.8 * max(0.0, math.cos(ph))
        h = [dx, bob]
        k = [h[0] + 0.42 * math.sin(th), h[1] + 0.42 * math.cos(th)]
        return h, k, [k[0] + 0.42 * math.sin(th - fl), k[1] + 0.42 * math.cos(th - fl)]

    def arm(ph: float, dx: float):
        a = 0.5 * math.sin(ph)
        s = [sh[0] + dx, sh[1]]
        e = [s[0] + 0.27 * math.sin(a), s[1] + 0.27 * math.cos(a)]
        return s, e, [e[0] + 0.25 * math.sin(a + 0.55), e[1] + 0.25 * math.cos(a + 0.55)]

    p[11], p[13], p[15] = leg(phase, -0.06)
    p[12], p[14], p[16] = leg(phase + math.pi, 0.06)
    p[5], p[7], p[9] = arm(phase + math.pi, -0.1)
    p[6], p[8], p[10] = arm(phase, 0.1)
    n = [sh[0] + 0.06, sh[1] - 0.2]
    p[0] = n
    p[1], p[2] = [n[0] - 0.03, n[1] - 0.04], [n[0] + 0.01, n[1] - 0.045]
    p[3], p[4] = [n[0] - 0.08, n[1] - 0.02], [n[0] + 0.04, n[1] - 0.03]
    return p


@dataclass
class Actor:
    track_id: int
    x0: float                      # начальная позиция бедра по x, пиксели
    speed: float                   # пиксели в секунду, знак — направление
    fall_at: Optional[float] = None
    fall_duration: float = 0.8
    height_px: float = 300.0


class SyntheticScene:
    """Кадры сцены 640×480 с частотой fps. t — секунды от начала."""

    def __init__(self, actors: List[Actor], camera_id: str = "cam_01", width: int = 640, height: int = 480,
                 floor_y: float = 440.0, t0: float = 0.0) -> None:
        self.actors, self.camera_id = actors, camera_id
        self.width, self.height, self.floor_y, self.t0 = width, height, floor_y, t0

    def pose(self, a: Actor, t: float) -> PersonPose:
        u = a.height_px / 1.75  # пикселей в единице тела (рост ≈ 1,75 единицы)
        t_move = t if a.fall_at is None else min(t, a.fall_at)
        hip_x = a.x0 + a.speed * t_move
        if self.width - 40 < hip_x or hip_x < 40:  # разворот у края кадра
            hip_x = max(40.0, min(self.width - 40.0, hip_x))
        phase = t_move * 6.0 * (1 if a.speed else 0)
        pts = walk_pose(phase if a.speed else 0.0)
        theta = 0.0
        if a.fall_at is not None and t > a.fall_at:
            k = min(1.0, (t - a.fall_at) / a.fall_duration)
            theta = (math.pi / 2 * 0.97) * (k * k)  # падение ускоряется
        side = 1 if a.speed >= 0 else -1
        feet = (hip_x, self.floor_y)
        kps = []
        for x, y in pts:
            qx, qy = x * side * u, (y - FEET_Y) * u
            rx = qx * math.cos(theta) - qy * math.sin(theta) * side
            ry = qx * math.sin(theta) * side + qy * math.cos(theta)
            kps.append((feet[0] + rx, min(self.floor_y, feet[1] + ry), 0.9))
        xs, ys = [k[0] for k in kps], [k[1] for k in kps]
        pad = 0.08 * a.height_px
        bbox = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad / 2)
        return PersonPose(track_id=a.track_id, bbox=bbox, keypoints=kps, score=0.9)

    def observation(self, frame_id: int, t: float) -> Observation:
        return Observation(camera_id=self.camera_id, frame_id=frame_id, t=self.t0 + t,
                           width=self.width, height=self.height,
                           people=[self.pose(a, t) for a in self.actors])

    def frames(self, duration: float, fps: float = 15.0):
        n = int(duration * fps)
        for i in range(n):
            yield self.observation(i, i / fps)

    def render(self, obs: Observation):
        """Картинка кадра для демо-потока: пол, сетка, люди-силуэты. Нужен OpenCV."""
        import cv2
        import numpy as np

        img = np.full((self.height, self.width, 3), (22, 16, 12), np.uint8)
        for x in range(0, self.width, 40):
            cv2.line(img, (x, 0), (x, self.height), (40, 32, 26), 1)
        cv2.line(img, (0, int(self.floor_y) + 2), (self.width, int(self.floor_y) + 2), (90, 80, 70), 2)
        cv2.putText(img, "SYNTHETIC CAMERA", (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 110, 100), 1, cv2.LINE_AA)
        return img


def demo_scene(t0: float = 0.0, fall_at: float = 6.0) -> SyntheticScene:
    """Сцена демо: один идёт и падает, второй просто ходит."""
    return SyntheticScene([Actor(1, 140, 40.0, fall_at=fall_at), Actor(2, 560, -30.0)], t0=t0)
