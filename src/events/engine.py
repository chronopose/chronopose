"""Движок событий (SCRUM-56): НОРМА → ПОДОЗРЕНИЕ → ПОДТВЕРЖДЕНО → ОПОВЕЩЕНИЕ → ВОССТАНОВЛЕНИЕ.

Один FallEngine — один человек (трек). Событие выдаётся ровно один раз за падение.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts import Event


@dataclass
class FallEngine:
    threshold: float = 0.6        # вероятность падения после слияния
    confirm_windows: int = 3      # сколько окон подряд нужно для подтверждения
    recover_windows: int = 4      # сколько «нормальных» окон, чтобы снять тревогу
    state: str = "NORMAL"
    _hits: int = 0
    _calm: int = 0
    _start: float = 0.0
    events: List[Event] = field(default_factory=list)

    def step(self, t: float, p_fall: float, imu_peak: Optional[bool], person: str = "P-001",
             camera_id: str = "cam_01", zone: str = "A") -> Optional[Event]:
        """Один шаг по окну 2 с. imu_peak: True — удар, False — удара нет, None — датчика нет."""
        hit = p_fall >= self.threshold
        if self.state in ("NORMAL", "SUSPECTED"):
            if hit:
                self._hits += 1
                if self._hits == 1:
                    self._start, self.state = t, "SUSPECTED"
                if self._hits >= self.confirm_windows or (imu_peak and self._hits >= 2):
                    self.state = "ALERT_SENT"
                    ev = Event(person=person, camera_id=camera_id, zone=zone, t_start=self._start,
                               t_confirmed=t, confidence=round(p_fall, 2), imu_confirmed=imu_peak)
                    self.events.append(ev)
                    return ev
            else:
                self._hits, self.state = 0, "NORMAL"
        elif self.state == "ALERT_SENT":
            self._calm = self._calm + 1 if not hit else 0
            if self._calm >= self.recover_windows:
                self.state, self._hits, self._calm = "NORMAL", 0, 0
        return None
