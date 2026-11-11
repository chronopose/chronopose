"""Гейт качества: прогоняет систему по всем записям eval/recordings и сравнивает с eval/baseline.json.

PR не сливается, если упала полнота, выросло число ложных тревог
или задержка вышла за KPI проекта (4 с от падения до текста).

    python scripts/eval_gate.py                    # проверить
    python scripts/eval_gate.py --update-baseline  # принять новые метрики как базу (только в PR с объяснением)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.replay import load, run

RECORDINGS = ROOT / "eval" / "recordings"
BASELINE = ROOT / "eval" / "baseline.json"
KPI_LATENCY_S = 4.0
LATENCY_SLACK_S = 0.5


def measure() -> tuple[dict, list[dict]]:
    rows, falls, found, false_alarms, lat = [], 0, 0, 0, []
    for path in sorted(RECORDINGS.glob("*.jsonl")):
        rec = load(path)
        res = run(rec)
        falls += res.falls
        found += len(res.matched)
        false_alarms += res.false_alarms
        lat += list(res.matched.values())
        rows.append({"запись": res.name, "синтетика": rec.meta.get("synthetic", False), "падений": res.falls,
                     "найдено": len(res.matched), "ложных": res.false_alarms,
                     "задержка, с": ", ".join(f"{v:.1f}" for v in res.matched.values()) or "—"})
    metrics = {
        "recordings": len(rows),
        "falls": falls,
        "recall": round(found / falls, 3) if falls else 1.0,
        "false_alarms": false_alarms,
        "latency_max_s": max(lat) if lat else 0.0,
        "latency_mean_s": round(sum(lat) / len(lat), 3) if lat else 0.0,
    }
    return metrics, rows


def check(m: dict, base: dict) -> list[str]:
    errors = []
    if m["recall"] < base["recall"]:
        errors.append(f"полнота упала: {m['recall']} < {base['recall']}")
    if m["false_alarms"] > base["false_alarms"]:
        errors.append(f"ложных тревог больше: {m['false_alarms']} > {base['false_alarms']}")
    if m["latency_max_s"] > KPI_LATENCY_S:
        errors.append(f"задержка {m['latency_max_s']} с больше KPI {KPI_LATENCY_S} с")
    elif m["latency_max_s"] > base["latency_max_s"] + LATENCY_SLACK_S:
        errors.append(f"задержка выросла: {m['latency_max_s']} > {base['latency_max_s']} + {LATENCY_SLACK_S} с")
    return errors


def table(rows: list[dict]) -> str:
    head = list(rows[0])
    out = ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
    out += ["| " + " | ".join(str(r[h]) for h in head) + " |" for r in rows]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--update-baseline", action="store_true")
    a = p.parse_args(argv)
    m, rows = measure()
    if a.update_baseline:
        BASELINE.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("база обновлена:", m)
        return 0
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    errors = check(m, base)
    report = (f"## Качество на наборе eval\n\n{table(rows)}\n\n"
              f"Полнота **{m['recall']}** (база {base['recall']}) · ложных тревог **{m['false_alarms']}** "
              f"(база {base['false_alarms']}) · задержка макс. **{m['latency_max_s']} с** (KPI ≤ {KPI_LATENCY_S} с)\n\n"
              + ("\n".join(f"- ❌ {e}" for e in errors) if errors else "✅ Не хуже базы\n"))
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report + "\n")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
