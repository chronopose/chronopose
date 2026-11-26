"""MQTT-приёмник IMU (SCRUM-49): принимает cps/imu/+/telemetry, хранит последние секунды,
отвечает на вопрос «был ли удар в этом окне?» и знает, жив ли датчик.

Удар = модуль ускорения отклонился от медианы окна больше порога. Так одинаково работают
и «ускорение с g» (≈ 9,8 в покое), и «без g» (≈ 0) из phyphox.
"""
# src/iot/receiver.py
from __future__ import annotations
import math
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional, Tuple
from src.contracts import ImuSample  # Pydantic-модель из проекта

IMPACT_MS2 = 12.0      # Порог удара (м/с²)
OFFLINE_AFTER_S = 2.0  # Если данных нет дольше — датчик офлайн

class ImuReceiver:
    def __init__(self, bus=None, keep_s: float = 10.0, impact_ms2: float = IMPACT_MS2, clock: Callable[[], float] = time.time) -> None:
        self.keep_s = keep_s
        self.impact_ms2 = impact_ms2
        self.clock = clock
        self.samples: Dict[str, Deque[Tuple[float, float]]] = {}
        self.last_seen: Dict[str, float] = {}
        self.errors: Dict[str, str] = {}
        self._lock = threading.Lock()
        
        if bus is not None:
            bus.subscribe("cps/imu/+/telemetry", self.on_telemetry)
            bus.subscribe("cps/imu/+/status", self.on_status)

    def on_telemetry(self, topic: str, payload: dict) -> None:
        try:
            s = ImuSample.model_validate(payload)
            self.add(s)
        except ValueError:
            pass  # Игнорируем битые пакеты

    def on_status(self, topic: str, payload: dict) -> None:
        device = topic.split("/")[2]
        if payload.get("ok") is False:
            self.errors[device] = str(payload.get("error", "ошибка"))
        else:
            self.errors.pop(device, None)

    def add(self, s: ImuSample) -> None:
        mag = math.sqrt(sum(v * v for v in s.acc))
        with self._lock:
            q = self.samples.setdefault(s.device_id, deque())
            q.append((s.t_server, mag))
            while q and s.t_server - q[0][0] > self.keep_s:
                q.popleft()
            self.last_seen[s.device_id] = max(self.last_seen.get(s.device_id, 0.0), s.t_server)

    def online(self, device: str) -> bool:
        return self.clock() - self.last_seen.get(device, -1e9) <= OFFLINE_AFTER_S

    def impact(self, device: str, t_start: float, t_end: float) -> Optional[bool]:
        """True — удар был; False — данных достаточно, удара нет; None — данных за окно нет."""
        with self._lock:
            q = list(self.samples.get(device, ()))
            win = [m for t, m in q if t_start <= t <= t_end]
            if len(win) < 5:
                return None
            base = sorted(win)[len(win) // 2]
            return max(abs(m - base) for m in win) >= self.impact_ms2

    def status(self) -> Dict[str, dict]:
        now = self.clock()
        with self._lock:
            return {
                d: {"online": self.online(d), "last_seen": now - self.last_seen.get(d, now), "error": self.errors.get(d)}
                for d in sorted(set(self.last_seen) | set(self.errors))
            }
