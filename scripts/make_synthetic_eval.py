"""Синтетические записи для eval/recordings — заглушка до реальных записей с телефонов.

Каждая запись помечена "synthetic": true. Когда команда запишет настоящие прогоны
(видео → поза → классификатор, IMU с телефона), их кладут рядом с "synthetic": false,
а синтетику постепенно удаляют. Генерация детерминирована (фиксированный seed).

    python scripts/make_synthetic_eval.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "eval" / "recordings"
HOP = 0.5


def scenario(name, seconds, falls=(), imu=True, spikes=(), note=""):
    rnd = random.Random(name)
    rows = []
    for i in range(1, int(seconds / HOP) + 1):
        t = round(i * HOP, 2)
        p = rnd.uniform(0.02, 0.35)
        peak = False
        for f in falls:
            dt = t - f
            if 0 < dt <= 3.0:          # падение и первые секунды на полу: классификатор уверен
                p = rnd.uniform(0.72, 0.96)
            elif 3.0 < dt <= 8.0:      # лежит: «падение» уже не похоже, класс «лежит»
                p = rnd.uniform(0.2, 0.45)
            if imu and 0 < dt <= 1.0:  # удар по датчику на поясе
                peak = True
        for s, val in spikes:          # ложные всплески: присел, наклонился
            if abs(t - s) < 1e-6:
                p = val
        rows.append({"t": t, "p_fall": round(p, 3), "imu_peak": peak if imu else None})
    meta = {"name": name, "hop_s": HOP, "falls": list(falls), "synthetic": True, "note": note}
    return meta, rows


SCENARIOS = [
    scenario("fall_with_imu", 30, falls=[12.0], note="падение на мат, телефон на поясе"),
    scenario("fall_no_imu", 30, falls=[10.0], imu=False, note="датчик молчит — решает только видео"),
    scenario("two_falls", 40, falls=[8.0, 24.0], note="два падения подряд, после каждого — подъём"),
    scenario("walk_only", 40, spikes=[(15.0, 0.68)], note="ходьба, один ложный всплеск на одном окне"),
    scenario("sit_down", 30, spikes=[(9.0, 0.63), (9.5, 0.66)], imu=False,
             note="резко сел на стул: два окна выше порога"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for meta, rows in SCENARIOS:
        lines = [json.dumps({"meta": meta}, ensure_ascii=False)] + [json.dumps(r) for r in rows]
        (OUT / f"{meta['name']}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("записано", meta["name"], len(rows), "окон")


if __name__ == "__main__":
    main()
