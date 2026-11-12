"""Обучение Random Forest «стоит / идёт / падает / лежит» и сравнение с правилами (SCRUM-40).

Пока реальных записей нет (SCRUM-87), данные — разнообразная синтетика: разный рост, скорость,
длительность падения, дрожание точек, пропуски кадров и трудные «не падения» — наклон к полу
и приседание. Деление на обучение и проверку — по «участникам» (сценам), а не по окнам,
иначе соседние окна одной сцены попадут в обе части и метрика будет завышена.

    python scripts/train_classifier.py                # обучить, вывести Macro-F1, сохранить модель
    python scripts/train_classifier.py --scenes 400
Результат: models/fall_forest.joblib (в git не попадает) и eval/classifier_metrics.json.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from src.contracts import ACTIONS, PersonPose  # noqa: E402
from src.models.classifier import RuleClassifier  # noqa: E402
from src.models.preprocess import SkeletonBuffer, feature_vector, features  # noqa: E402
from src.vision.synthetic import Actor, SyntheticScene  # noqa: E402

FPS, HOP, WIN = 15.0, 0.5, 2.0


def _tilt(p: PersonPose, angle: float, drop: float) -> PersonPose:
    """Наклон туловища вперёд вокруг бёдер (angle, рад) и приседание (drop, пиксели)."""
    k = [list(v) for v in p.keypoints]
    hx = (k[11][0] + k[12][0]) / 2
    hy = (k[11][1] + k[12][1]) / 2
    for i in range(0, 11):  # голова, плечи, руки
        dx, dy = k[i][0] - hx, k[i][1] - hy
        k[i][0] = hx + dx * math.cos(angle) - dy * math.sin(angle)
        k[i][1] = hy + dx * math.sin(angle) + dy * math.cos(angle) + drop
    for i in (11, 12):
        k[i][1] += drop
    for i in (13, 14):
        k[i][1] += drop * 0.5
    return p.model_copy(update={"keypoints": [tuple(v) for v in k]})


def scene_windows(seed: int) -> Tuple[List[List[float]], List[str]]:
    rnd = random.Random(seed)
    kind = rnd.choice(["walk", "stand", "fall", "fall", "bend", "squat"])
    speed = 0.0 if kind == "stand" else rnd.choice([-1, 1]) * rnd.uniform(15, 70)
    actor = Actor(1, rnd.uniform(120, 520), speed if kind != "squat" else 0.0,
                  fall_at=rnd.uniform(3.0, 5.0) if kind == "fall" else None,
                  fall_duration=rnd.uniform(0.5, 1.2), height_px=rnd.uniform(180, 380))
    if kind in ("bend", "squat"):
        actor.speed = rnd.uniform(-10, 10)
    scene = SyntheticScene([actor])
    t_event = rnd.uniform(3.0, 5.0)
    jitter, dropout = rnd.uniform(0.5, 4.0), rnd.uniform(0.0, 0.15)
    buf, X, y = SkeletonBuffer(), [], []
    next_t = WIN
    for obs in scene.frames(10.0, fps=FPS):
        t = obs.t
        p = obs.people[0]
        if kind in ("bend", "squat") and t_event <= t <= t_event + 2.5:
            u = math.sin(math.pi * (t - t_event) / 2.5)
            p = _tilt(p, math.radians(rnd.uniform(55, 70)) * u, 0.0) if kind == "bend" else _tilt(p, 0.2 * u, 90 * u)
        pts = [(x + rnd.gauss(0, jitter), yy + rnd.gauss(0, jitter), c if rnd.random() > dropout else 0.1)
               for x, yy, c in p.keypoints]
        if rnd.random() > dropout:
            buf.add(t, p.model_copy(update={"keypoints": pts}))
        if t + 1e-9 < next_t:
            continue
        next_t += HOP
        f = features(buf.window(t, WIN), WIN)
        if f is None or f["coverage"] < 0.6:
            continue
        if kind == "fall" and actor.fall_at is not None and t > actor.fall_at:
            since = t - actor.fall_at
            if since < 0.3:
                continue                       # переходные окна не размечаем
            label = "fall" if since <= actor.fall_duration + 1.4 else "lie"
            if actor.fall_duration + 1.4 < since < actor.fall_duration + 2.2:
                continue
        elif kind in ("stand", "squat") or abs(speed) < 12 or (kind == "bend"):
            label = "stand"
        else:
            label = "walk"
        X.append(feature_vector(f))
        y.append(label)
    return X, y


def dataset(scenes: int, offset: int = 0):
    X, y, g = [], [], []
    for s in range(offset, offset + scenes):
        xs, ys = scene_windows(s)
        X += xs
        y += ys
        g += [s] * len(xs)
    return np.array(X), np.array(y), np.array(g)


def macro_f1(y_true, y_pred) -> Tuple[float, dict]:
    from sklearn.metrics import confusion_matrix, f1_score

    f1 = float(f1_score(y_true, y_pred, labels=ACTIONS, average="macro", zero_division=0))
    cm = confusion_matrix(y_true, y_pred, labels=ACTIONS).tolist()
    return f1, {"labels": ACTIONS, "matrix": cm}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scenes", type=int, default=300)
    p.add_argument("--out", default=str(ROOT / "models" / "fall_forest.joblib"))
    p.add_argument("--metrics", default=str(ROOT / "eval" / "classifier_metrics.json"))
    a = p.parse_args(argv)
    import joblib
    from sklearn.ensemble import RandomForestClassifier

    n_val = a.scenes // 4
    Xtr, ytr, _ = dataset(a.scenes - n_val, 0)
    Xva, yva, _ = dataset(n_val, 10_000)      # другие «участники»: сцены с иными seed
    rf = RandomForestClassifier(n_estimators=200, max_depth=10, min_samples_leaf=3, class_weight="balanced",
                                random_state=0, n_jobs=-1).fit(Xtr, ytr)
    f1_rf, cm_rf = macro_f1(yva, rf.predict(Xva))
    rules = RuleClassifier()
    keys = ["angle_end", "angle_change", "angle_std", "drop", "vdown", "speed_x", "aspect_end", "coverage"]
    pred_rules = [max(pr, key=pr.get) for pr in (rules.predict_proba(dict(zip(keys, x))) for x in Xva)]
    f1_rules, cm_rules = macro_f1(yva, pred_rules)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(rf, a.out)
    metrics = {"data": "synthetic", "train_windows": int(len(ytr)), "val_windows": int(len(yva)),
               "val_split": "по сценам (участникам)",
               "macro_f1": {"forest": round(f1_rf, 3), "rules": round(f1_rules, 3)},
               "confusion": {"forest": cm_rf, "rules": cm_rules},
               "class_counts_val": {k: int((yva == k).sum()) for k in ACTIONS}}
    Path(a.metrics).write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
                                                           encoding="utf-8")
    print(json.dumps(metrics["macro_f1"]), "окон:", len(ytr), "/", len(yva))
    print("матрица ошибок (forest), строки — истина:", ACTIONS)
    for lab, row in zip(ACTIONS, cm_rf["matrix"]):
        print(f"  {lab:6s} {row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
