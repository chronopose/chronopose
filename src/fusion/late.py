"""Позднее слияние с флагами доступности источников (SCRUM-54).

Решение принимает видео: оно знает, кто упал. Датчик — второй свидетель:
- удар есть → вероятность падения чуть выше, и движок подтверждает событие на окно раньше;
- удара нет → вероятность не снижаем (телефон мог лежать в кармане свободно);
- датчика нет → работаем по видео, в тексте оповещения так и пишем.
"""
from __future__ import annotations

from typing import Optional

from src.contracts import ActionPrediction, FusedWindow

IMU_BOOST = 0.15


def fuse(pred: ActionPrediction, imu_peak: Optional[bool]) -> FusedWindow:
    p_video = pred.p_fall
    p = min(1.0, p_video + IMU_BOOST) if imu_peak and p_video >= 0.3 else p_video
    return FusedWindow(camera_id=pred.camera_id, track_id=pred.track_id, t_end=pred.t_end,
                       p_video=p_video, imu_peak=imu_peak, p_fall=round(p, 4),
                       sources={"video": True, "imu": imu_peak is not None})
