"""Детекция позы и трекинг (SCRUM-31, SCRUM-33).

Интерфейс один: `estimator(frame, t) -> list[PersonPose]` с устойчивыми track_id.
- YoloPoseTracker — YOLO26n-pose + ByteTrack из ultralytics (pip install -r requirements-vision.txt).
- IouTracker — простой трекинг для детекторов без своих номеров.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Protocol

from src.contracts import PersonPose


class PoseEstimator(Protocol):
    def __call__(self, frame, t: float) -> List[PersonPose]: ...


class YoloPoseTracker:
    """YOLO-pose с ByteTrack. Модель скачивается ultralytics при первом запуске."""

    def __init__(self, model: str = "yolo26n-pose.pt", tracker: str = "bytetrack.yaml",
                 conf: float = 0.4, imgsz: int = 640, device: Optional[str] = None) -> None:
        from ultralytics import YOLO

        self.model = YOLO(model)
        self.tracker, self.conf, self.imgsz, self.device = tracker, conf, imgsz, device

    def __call__(self, frame, t: float) -> List[PersonPose]:
        res = self.model.track(frame, persist=True, tracker=self.tracker, conf=self.conf,
                               imgsz=self.imgsz, device=self.device, verbose=False, classes=[0])[0]
        if res.keypoints is None or res.boxes is None or len(res.boxes) == 0:
            return []
        boxes = res.boxes.xyxy.cpu().numpy()
        ids = res.boxes.id.cpu().numpy().astype(int) if res.boxes.id is not None else [-1] * len(boxes)
        scores = res.boxes.conf.cpu().numpy()
        kxy = res.keypoints.xy.cpu().numpy()
        kconf = res.keypoints.conf.cpu().numpy() if res.keypoints.conf is not None else None
        people = []
        for i, box in enumerate(boxes):
            pts = [(float(x), float(y), float(kconf[i][j]) if kconf is not None else 1.0)
                   for j, (x, y) in enumerate(kxy[i])]
            people.append(PersonPose(track_id=int(ids[i]), bbox=tuple(float(v) for v in box),
                                     keypoints=pts, score=float(scores[i])))
        return people


def iou(a, b) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class IouTracker:
    """Жадное сопоставление по IoU с прошлым кадром. Трек живёт max_age кадров без совпадений."""

    def __init__(self, min_iou: float = 0.25, max_age: int = 15) -> None:
        self.min_iou, self.max_age = min_iou, max_age
        self.tracks: Dict[int, dict] = {}
        self.next_id = 1

    def update(self, people: List[PersonPose]) -> List[PersonPose]:
        pairs = sorted(((iou(tr["bbox"], p.bbox), tid, i) for tid, tr in self.tracks.items()
                        for i, p in enumerate(people)), reverse=True)
        used_t, used_p, out = set(), set(), [None] * len(people)
        for score, tid, i in pairs:
            if score < self.min_iou or tid in used_t or i in used_p:
                continue
            used_t.add(tid)
            used_p.add(i)
            out[i] = people[i].model_copy(update={"track_id": tid})
        for i, p in enumerate(people):
            if out[i] is None:
                out[i] = p.model_copy(update={"track_id": self.next_id})
                self.next_id += 1
        for tid in list(self.tracks):
            if tid not in used_t:
                self.tracks[tid]["age"] += 1
                if self.tracks[tid]["age"] > self.max_age:
                    del self.tracks[tid]
        for p in out:
            self.tracks[p.track_id] = {"bbox": p.bbox, "age": 0}
        return out
