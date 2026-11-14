"""Отрисовка скелетов, номеров и действий поверх кадра (SCRUM-78)."""
from __future__ import annotations

from typing import Dict, Optional

from src.contracts import ACTION_RU, SKELETON_EDGES, Observation

CYAN, RED, WHITE = (225, 235, 239), (0, 61, 242), (225, 235, 239)  # BGR: бумага, оранжевый


def draw_overlay(img, obs: Observation, labels: Optional[Dict[int, str]] = None,
                 alarm: Optional[set] = None, min_conf: float = 0.3):
    import cv2

    labels, alarm = labels or {}, alarm or set()
    for p in obs.people:
        col = RED if p.track_id in alarm else CYAN
        k = p.keypoints
        for a, b in SKELETON_EDGES:
            if k[a][2] >= min_conf and k[b][2] >= min_conf:
                cv2.line(img, (int(k[a][0]), int(k[a][1])), (int(k[b][0]), int(k[b][1])), col, 3, cv2.LINE_AA)
        for x, y, c in k[5:]:
            if c >= min_conf:
                cv2.circle(img, (int(x), int(y)), 4, (12, 14, 14), -1, cv2.LINE_AA)
                cv2.circle(img, (int(x), int(y)), 4, col, 2, cv2.LINE_AA)
        x1, y1, x2, y2 = (int(v) for v in p.bbox)
        cv2.rectangle(img, (x1, y1), (x2, y2), col, 1)
        act = labels.get(p.track_id, "")
        text = f"ID {p.track_id:03d} {act.upper()}" if act else f"ID {p.track_id:03d}"
        cv2.rectangle(img, (x1, max(0, y1 - 22)), (x1 + 9 * len(text) + 10, y1), col, -1)
        cv2.putText(img, text, (x1 + 5, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1, cv2.LINE_AA)
    return img


def action_label(label: str) -> str:
    """Подпись для кадра латиницей: OpenCV не рисует кириллицу шрифтами Hershey."""
    return {"stand": "standing", "walk": "walking", "fall": "FALLING", "lie": "lying"}.get(label, label)


__all__ = ["draw_overlay", "action_label", "ACTION_RU"]
