"""Шаблонный генератор оповещений (SCRUM-57): в тексте только поля события, ничего не выдумываем."""
from __future__ import annotations

from datetime import datetime

from src.contracts import Alert, Event

IMU_TEXT = {True: "датчик на поясе подтвердил удар", False: "датчик удара не зафиксировал",
            None: "подтверждения датчика нет"}


def render(ev: Event) -> str:
    t = datetime.fromtimestamp(ev.t_start).strftime("%H:%M:%S")
    return (f"В {t} в зоне {ev.zone} возможное падение человека {ev.person}. "
            f"Камера {ev.camera_id}, уверенность видео {round(ev.confidence * 100)} %, {IMU_TEXT[ev.imu_confirmed]}.")


def make_alert(ev: Event) -> Alert:
    return Alert(event_id=ev.id, t=ev.t_confirmed, text=render(ev), person=ev.person, camera_id=ev.camera_id,
                 zone=ev.zone, confidence=ev.confidence, imu_confirmed=ev.imu_confirmed)
