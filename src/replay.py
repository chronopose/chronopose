"""Прогон системы по записи — без камеры, телефонов и сети.

Запись — JSONL: первая строка {"meta": {...}}, дальше по строке на окно:
    {"t": 12.5, "p_fall": 0.82, "imu_peak": true}
t — конец окна в секундах, p_fall — вероятность падения от классификатора,
imu_peak — был ли удар по датчику (null = датчик молчит).
В meta: name, hop_s, falls (истинные моменты падений), synthetic.

Зачем:
  1. CI: прогон «падение → оповещение» на каждом PR (tests/test_replay.py).
  2. Оценка качества: scripts/eval_gate.py считает полноту, ложные тревоги, задержку.
  3. Запасной режим демо: если Wi-Fi в аудитории подведёт —
     python -m src.replay eval/recordings/fall_with_imu.jsonl --realtime [--mqtt 192.168.1.10]
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.alerts.generator import render
from src.events.engine import Event, FallEngine

MATCH_WINDOW_S = 6.0  # тревога засчитывается падению, если пришла в течение 6 с после него


@dataclass
class Recording:
    meta: dict
    windows: list[dict]

    @property
    def falls(self) -> list[float]:
        return list(self.meta.get("falls", []))


@dataclass
class RunResult:
    name: str
    alerts: list[tuple[float, Event]] = field(default_factory=list)  # (время выдачи, событие)
    matched: dict[float, float] = field(default_factory=dict)        # падение → задержка
    false_alarms: int = 0
    falls: int = 0


def load(path: str | Path) -> Recording:
    lines = [json.loads(s) for s in Path(path).read_text(encoding="utf-8").splitlines() if s.strip()]
    return Recording(meta=lines[0]["meta"], windows=lines[1:])


def run(rec: Recording, engine: FallEngine | None = None, on_alert=None, realtime: bool = False) -> RunResult:
    eng = engine or FallEngine()
    res = RunResult(name=rec.meta.get("name", "?"), falls=len(rec.falls))
    prev_t = None
    for w in rec.windows:
        if realtime and prev_t is not None:
            time.sleep(max(0.0, w["t"] - prev_t))
        prev_t = w["t"]
        ev = eng.step(w["t"], float(w["p_fall"]), bool(w.get("imu_peak")))
        if ev:
            res.alerts.append((w["t"], ev))
            if on_alert:
                on_alert(ev)
    for t_emit, _ in res.alerts:
        fall = next((f for f in rec.falls if f not in res.matched and 0 <= t_emit - f <= MATCH_WINDOW_S), None)
        if fall is None:
            res.false_alarms += 1
        else:
            res.matched[fall] = round(t_emit - fall, 3)
    return res


def _mqtt_publisher(host: str):
    import paho.mqtt.client as mqtt  # нужен только для демо

    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="replay")
    cli.connect(host, 1883)
    cli.loop_start()
    return lambda ev: cli.publish("cps/alerts", json.dumps({"text": render(ev), "person": ev.person}, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Прогон системы по записи")
    p.add_argument("recording")
    p.add_argument("--realtime", action="store_true", help="идти в темпе записи (для демо)")
    p.add_argument("--mqtt", help="адрес Mosquitto: оповещения уйдут в cps/alerts, ESP32 мигнёт")
    a = p.parse_args(argv)
    send = _mqtt_publisher(a.mqtt) if a.mqtt else None

    def on_alert(ev: Event) -> None:
        print(render(ev), flush=True)
        if send:
            send(ev)

    res = run(load(a.recording), on_alert=on_alert, realtime=a.realtime)
    print(f"падений {res.falls}, найдено {len(res.matched)}, ложных тревог {res.false_alarms}, задержки {res.matched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
