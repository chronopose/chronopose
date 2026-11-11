"""Шаблонный генератор оповещений (SCRUM-57): в тексте только поля события."""
from __future__ import annotations

from datetime import datetime

from src.events.engine import Event


def render(ev: Event) -> str:
    t = datetime.fromtimestamp(ev.t_start).strftime("%H:%M:%S")
    imu = "датчик на поясе подтвердил удар" if ev.imu_confirmed else "подтверждения датчика нет"
    return (f"В {t} в зоне {ev.zone} возможное падение человека {ev.person}. "
            f"Уверенность видео {round(ev.confidence * 100)} %, {imu}.")
