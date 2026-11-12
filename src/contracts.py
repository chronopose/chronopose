"""Контракты данных между модулями (SCRUM-6).

Один источник правды для форматов: камера → поза → действие → слияние → событие → оповещение.
Модели — Pydantic v2, сериализуются в JSON для MQTT, API и базы. Optional вместо «X | None»,
чтобы модели работали и на Python 3.9.
"""
from __future__ import annotations

import time
import uuid
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

# 17 ключевых точек COCO — так их отдаёт YOLO-pose
KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist",
    "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle",
]
SKELETON_EDGES = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12), (11, 12),
                  (11, 13), (13, 15), (12, 14), (14, 16), (0, 1), (0, 2), (1, 3), (2, 4)]
ACTIONS = ["stand", "walk", "fall", "lie"]
ACTION_RU = {"stand": "стоит", "walk": "идёт", "fall": "падает", "lie": "лежит"}

Point = Tuple[float, float, float]  # x, y в пикселях кадра; уверенность 0..1


class PersonPose(BaseModel):
    """Один человек в одном кадре."""
    track_id: int
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2
    keypoints: List[Point] = Field(min_length=17, max_length=17)
    score: float = 1.0


class Observation(BaseModel):
    """Результат зрения для одного кадра одной камеры."""
    camera_id: str
    frame_id: int
    t: float
    width: int
    height: int
    people: List[PersonPose] = []


class ImuSample(BaseModel):
    """Одно измерение носимого датчика (телефон на поясе). Топик cps/imu/{device_id}/telemetry."""
    device_id: str
    sequence: int
    t_phone: float
    t_server: float
    acc: Tuple[float, float, float]
    gyro: Optional[Tuple[Optional[float], Optional[float], Optional[float]]] = None


class ActionPrediction(BaseModel):
    """Классификация одного окна 2 с для одного трека."""
    camera_id: str
    track_id: int
    t_start: float
    t_end: float
    probs: Dict[str, float]

    @property
    def label(self) -> str:
        return max(self.probs, key=self.probs.get)

    @property
    def p_fall(self) -> float:
        return self.probs.get("fall", 0.0)


class FusedWindow(BaseModel):
    """Окно после слияния видео и датчика (SCRUM-53/54)."""
    camera_id: str
    track_id: int
    t_end: float
    p_video: Optional[float]
    imu_peak: Optional[bool]          # None — датчик молчит или не привязан
    p_fall: float
    sources: Dict[str, bool]          # {"video": True, "imu": False}


class Event(BaseModel):
    """Подтверждённое событие. Движок выдаёт его ровно один раз за падение."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    kind: Literal["possible_fall"] = "possible_fall"
    person: str = "P-001"
    camera_id: str = "cam_01"
    zone: str = "A"
    t_start: float
    t_confirmed: float = Field(default_factory=time.time)
    confidence: float
    imu_confirmed: Optional[bool] = None


class Alert(BaseModel):
    """Оповещение оператору: текст из шаблона по полям события. Топик cps/alerts."""
    event_id: str
    t: float
    text: str
    person: str
    camera_id: str
    zone: str
    confidence: float
    imu_confirmed: Optional[bool] = None
