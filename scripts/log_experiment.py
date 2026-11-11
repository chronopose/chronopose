"""Записать прогон оценки в MLflow: метрики гейта, параметры движка, коммит.

    pip install mlflow
    python scripts/log_experiment.py --name "порог 0.65" --param threshold=0.65
    mlflow ui            # http://127.0.0.1:5000 — сравнить запуски

Без MLflow скрипт просто печатает метрики. Папка mlruns/ в git не попадает.
ID запуска указывайте в PR, где меняются модель или пороги.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.eval_gate import measure
from src import replay
from src.events.engine import FallEngine


def parse_params(pairs: list[str]) -> dict:
    out = {}
    for pair in pairs:
        key, value = pair.split("=", 1)
        out[key] = int(value) if value.isdigit() else float(value)
    return out


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--name", default="eval")
    p.add_argument("--param", action="append", default=[], help="параметр движка, например threshold=0.65")
    a = p.parse_args(argv)
    params = parse_params(a.param)
    replay.FallEngine = lambda: FallEngine(**params)  # прогон с изменёнными параметрами
    metrics, rows = measure()
    print(metrics)
    try:
        import mlflow
    except ImportError:
        print("MLflow не установлен: pip install mlflow — метрики выше не сохранены")
        return 0
    mlflow.set_experiment("chronopose-eval")
    with mlflow.start_run(run_name=a.name) as run:
        mlflow.log_params({**{f.name: getattr(FallEngine(**params), f.name)
                              for f in FallEngine.__dataclass_fields__.values() if f.name[0] != "_"
                              and f.name not in ("state", "events")}, "git_sha": git_sha()})
        mlflow.log_metrics({k: float(v) for k, v in metrics.items()})
        mlflow.log_dict({"recordings": rows}, "per_recording.json")
        print("MLflow run:", run.info.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
