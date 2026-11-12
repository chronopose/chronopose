"""Симулятор телефона-IMU: ходьба 50 Гц и удар при падении. Для демо и тестов без телефона.

    python -m src.iot.simulator --broker localhost --fall-at 6     # в реальный MQTT
"""
from __future__ import annotations

import argparse
import math
import random
import time
from typing import Iterator, Optional

from src.contracts import ImuSample

G = 9.81


def samples(device: str = "imu_001", t0: float = 0.0, duration: float = 20.0, rate: float = 50.0,
            fall_at: Optional[float] = None, seed: int = 7, with_g: bool = True) -> Iterator[ImuSample]:
    rnd = random.Random(seed)
    n = int(duration * rate)
    for i in range(n):
        t = i / rate
        step = 1.8 * math.sin(2 * math.pi * 1.9 * t)  # шаги ~1,9 Гц
        az = (G if with_g else 0.0) + step + rnd.gauss(0, 0.3)
        ax, ay = rnd.gauss(0, 0.4) + 0.6 * math.sin(2 * math.pi * 0.95 * t), rnd.gauss(0, 0.4)
        if fall_at is not None and t >= fall_at:
            dt = t - fall_at
            if dt < 0.25:                      # свободное падение: модуль уходит к нулю
                ax, ay, az = ax * 0.2, ay * 0.2, az * 0.15
            elif dt < 0.4:                     # удар о мат
                ax, ay, az = 14.0 + rnd.gauss(0, 2), 9.0, 24.0 + rnd.gauss(0, 3)
            else:                              # лежит: g по другой оси, без шагов
                ax, ay, az = (G if with_g else 0.0) + rnd.gauss(0, 0.2), rnd.gauss(0, 0.2), rnd.gauss(0, 0.2)
        yield ImuSample(device_id=device, sequence=i + 1, t_phone=t, t_server=t0 + t,
                        acc=(ax, ay, az), gyro=(rnd.gauss(0, 0.1), rnd.gauss(0, 0.1), rnd.gauss(0, 0.1)))


def run(bus, device: str = "imu_001", fall_at: Optional[float] = 6.0, duration: float = 3600.0,
        realtime: bool = True) -> None:
    t0 = time.time()
    for s in samples(device, t0=t0, duration=duration, fall_at=fall_at):
        if realtime:
            time.sleep(max(0.0, s.t_server - time.time()))
        bus.publish(f"cps/imu/{device}/telemetry", s.model_dump())


if __name__ == "__main__":
    from src.bus import MqttBus

    p = argparse.ArgumentParser(description="Симулятор телефона-IMU")
    p.add_argument("--broker", default="localhost")
    p.add_argument("--device", default="imu_001")
    p.add_argument("--fall-at", type=float, default=6.0)
    a = p.parse_args()
    run(MqttBus(a.broker, client_id=f"sim-{a.device}"), a.device, a.fall_at)
