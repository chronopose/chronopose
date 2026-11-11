"""Движок событий MVP (SCRUM-56): НОРМА → ПОДОЗРЕНИЕ → ПОДТВЕРЖДЕНО → ОПОВЕЩЕНИЕ → ВОССТАНОВЛЕНИЕ."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Event:
    person: str
    kind: str
    t_start: float
    confidence: float
    imu_confirmed: bool
    zone: str = "зона A"


@dataclass
class FallEngine:
    threshold: float = 0.6        # вероятность падения по слитому прогнозу
    confirm_windows: int = 3      # сколько окон подряд нужно для подтверждения
    recover_windows: int = 4      # сколько «нормальных» окон, чтобы снять тревогу
    state: str = "NORMAL"
    _hits: int = 0
    _calm: int = 0
    _start: float = 0.0
    events: list[Event] = field(default_factory=list)

    def step(self, t: float, p_fall: float, imu_peak: bool, person: str = "P-001") -> Event | None:
        """Один шаг по окну 2 с. Возвращает событие ровно один раз за падение."""
        hit = p_fall >= self.threshold
        if self.state in ("NORMAL", "SUSPECTED"):
            if hit:
                self._hits += 1
                if self._hits == 1:
                    self._start, self.state = t, "SUSPECTED"
                if self._hits >= self.confirm_windows or (imu_peak and self._hits >= 2):
                    self.state = "ALERT_SENT"
                    ev = Event(person, "possible_fall", self._start, p_fall, imu_peak)
                    self.events.append(ev)
                    return ev
            else:
                self._hits, self.state = 0, "NORMAL"
        elif self.state == "ALERT_SENT":
            self._calm = self._calm + 1 if not hit else 0
            if self._calm >= self.recover_windows:
                self.state, self._hits, self._calm = "NORMAL", 0, 0
        return None
