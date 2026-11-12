"""Мост «телефон → MQTT» (SCRUM-47). Без закупок: IMU — это Android-смартфон на поясе.

На телефоне: приложение phyphox → эксперимент с акселерометром и гироскопом → «Разрешить удалённый доступ».
phyphox отдаёт данные по HTTP: http://<ip телефона>:8080/get?<буфер>=<с какого времени>.
Имена буферов зависят от эксперимента — проверьте их в phyphox и поправьте configs/devices.yaml.

Запуск: MQTT_USER=phone MQTT_PASSWORD=… python -m src.iot.phone_imu_bridge --phone 192.168.1.23 --device imu_001
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request

DEFAULT_BUFFERS = {"t": "acc_time", "ax": "accX", "ay": "accY", "az": "accZ",
                   "gx": "gyrX", "gy": "gyrY", "gz": "gyrZ"}


def poll(phone: str, buffers: dict[str, str], since: float) -> dict[str, list[float]]:
    q = "&".join(f"{b}={since}|{buffers['t']}" if k != "t" else f"{b}={since}" for k, b in buffers.items())
    with urllib.request.urlopen(f"http://{phone}:8080/get?{q}", timeout=2) as r:
        data = json.load(r)["buffer"]
    return {k: data[b]["buffer"] for k, b in buffers.items()}


def run(phone: str, device: str, broker: str, period: float = 0.2) -> None:
    from src.bus import MqttBus  # логин и пароль — MQTT_USER=phone, MQTT_PASSWORD

    bus = MqttBus(broker, client_id=f"bridge-{device}")
    since, seq = 0.0, 0
    while True:
        try:
            b = poll(phone, DEFAULT_BUFFERS, since)
        except OSError as e:
            bus.publish(f"cps/imu/{device}/status", {"ok": False, "error": str(e)})
            time.sleep(1)
            continue
        for i, t in enumerate(b["t"]):
            seq += 1
            msg = {"device_id": device, "sequence": seq, "t_phone": t, "t_server": time.time(),
                   "acc": [b["ax"][i], b["ay"][i], b["az"][i]],
                   "gyro": [b["gx"][i] if i < len(b["gx"]) else None,
                            b["gy"][i] if i < len(b["gy"]) else None,
                            b["gz"][i] if i < len(b["gz"]) else None]}
            bus.publish(f"cps/imu/{device}/telemetry", msg)
        if b["t"]:
            since = b["t"][-1]
        time.sleep(period)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--phone", required=True)
    p.add_argument("--device", default="imu_001")
    p.add_argument("--broker", default="localhost")
    a = p.parse_args()
    run(a.phone, a.device, a.broker)
