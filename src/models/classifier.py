"""Классификатор MVP (SCRUM-40): «стоит / идёт / падает / лежит».

RuleClassifier — правила по признакам позы, работает без обучения и объясним на защите.
ForestClassifier — Random Forest на тех же признаках (scripts/train_classifier.py).
Оба отдают вероятности по ACTIONS; движку событий нужна p(fall).
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Protocol

from src.contracts import ACTIONS
from src.models.preprocess import feature_vector


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, x))))


class Classifier(Protocol):
    def predict_proba(self, f: Dict[str, float]) -> Dict[str, float]: ...


class RuleClassifier:
    """Падение = туловище быстро повернулось к горизонтали и плечи резко ушли вниз."""

    def __init__(self, fall_angle: float = 40.0, fall_drop: float = 0.8, fall_vdown: float = 1.0,
                 lie_angle: float = 55.0, walk_speed: float = 0.2) -> None:
        self.fall_angle, self.fall_drop, self.fall_vdown = fall_angle, fall_drop, fall_vdown
        self.lie_angle, self.walk_speed = lie_angle, walk_speed

    def predict_proba(self, f: Dict[str, float]) -> Dict[str, float]:
        fall = (_sig((f["angle_change"] - self.fall_angle) / 8) * _sig((f["drop"] - self.fall_drop) / 0.25)
                * _sig((f["vdown"] - self.fall_vdown) / 0.3))
        lying = _sig((f["angle_end"] - self.lie_angle) / 8)
        upright = 1.0 - lying
        moving = _sig((f["speed_x"] - self.walk_speed) / 0.08)
        raw = {
            "fall": fall,
            "lie": lying * (1 - fall),
            "walk": upright * moving * (1 - fall),
            "stand": upright * (1 - moving) * (1 - fall),
        }
        s = sum(raw.values()) or 1.0
        return {k: raw[k] / s for k in ACTIONS}


class ForestClassifier:
    """Random Forest из файла joblib. Не найден файл — честная ошибка, без тихой подмены."""

    def __init__(self, path: str) -> None:
        import joblib

        self.model = joblib.load(path)

    def predict_proba(self, f: Dict[str, float]) -> Dict[str, float]:
        proba = self.model.predict_proba([feature_vector(f)])[0]
        out = {k: 0.0 for k in ACTIONS}
        for cls, p in zip(self.model.classes_, proba):
            out[str(cls)] = float(p)
        return out


def load_classifier(kind: str = "rules", path: Optional[str] = None) -> Classifier:
    if kind == "forest":
        return ForestClassifier(path or "models/fall_forest.joblib")
    return RuleClassifier()
