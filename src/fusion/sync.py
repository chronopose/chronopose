"""Совместные окна видео и IMU по меткам времени (SCRUM-53).

Видео и датчик живут на одной шкале — времени ноутбука (кадр: время приёма, IMU: t_server).
Окно видео [t_end − 2 с, t_end] расширяется на допуск, чтобы удар на границе окна не потерялся,
и сдвигается на измеренную задержку датчика imu_offset_s.

Привязка датчика к человеку в MVP — «к камере»: телефон на поясе у того, кто в кадре.
Если в кадре несколько людей, удар подтверждает того, у кого видео показывает падение.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from src.contracts import ActionPrediction


class WindowSync:
    def __init__(self, imu, devices: Dict[str, str], imu_offset_s: float = 0.0, tolerance_s: float = 0.5) -> None:
        self.imu = imu                # ImuReceiver или None
        self.devices = devices        # device_id → camera_id
        self.offset, self.tol = imu_offset_s, tolerance_s

    def devices_for(self, camera_id: str) -> List[str]:
        return [d for d, cam in self.devices.items() if cam == camera_id]

    def imu_peak(self, pred: ActionPrediction) -> Optional[bool]:
        """True/False — по данным датчиков камеры; None — датчика нет или он молчит."""
        if self.imu is None:
            return None
        results = [self.imu.impact(d, pred.t_start + self.offset - self.tol, pred.t_end + self.offset + self.tol)
                   for d in self.devices_for(pred.camera_id)]
        known = [r for r in results if r is not None]
        if not known:
            return None
        return any(known)
