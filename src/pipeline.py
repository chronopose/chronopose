"""Сквозной конвейер MVP (SCRUM-86): кадр → поза → окна 2 с → действие → слияние с IMU → событие → оповещение.

Конвейер не знает, откуда пришло наблюдение (телефон, файл, синтетика) и куда уходит
оповещение (MQTT для ESP32, база, WebSocket демо-панели) — это задаётся снаружи.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from src.alerts.generator import make_alert
from src.contracts import ActionPrediction, Alert, Event, Observation
from src.events.engine import FallEngine
from src.fusion.late import fuse
from src.fusion.sync import WindowSync
from src.models.classifier import Classifier, RuleClassifier
from src.models.preprocess import SkeletonBuffer, features

log = logging.getLogger("pipeline")


@dataclass
class TrackState:
    buffer: SkeletonBuffer = field(default_factory=SkeletonBuffer)
    engine: FallEngine = field(default_factory=FallEngine)
    label: str = "stand"
    probs: Dict[str, float] = field(default_factory=dict)
    last_t: float = 0.0
    fused: Optional[dict] = None


class Pipeline:
    def __init__(self, bus=None, store=None, imu=None, devices: Optional[Dict[str, str]] = None,
                 classifier: Optional[Classifier] = None, zones: Optional[Dict[str, str]] = None,
                 window_s: float = 2.0, hop_s: float = 0.5, forget_s: float = 5.0) -> None:
        self.bus, self.store = bus, store
        self.classifier = classifier or RuleClassifier()
        self.sync = WindowSync(imu, devices or {})
        self.zones = zones or {}
        self.window_s, self.hop_s, self.forget_s = window_s, hop_s, forget_s
        self.tracks: Dict[Tuple[str, int], TrackState] = {}
        self.next_eval: Dict[str, float] = {}
        self.last_obs: Dict[str, Observation] = {}
        self.alerts: List[Alert] = []
        self.listeners: List[Callable[[Alert], None]] = []
        self._lock = threading.Lock()

    def on_observation(self, obs: Observation) -> List[Alert]:
        with self._lock:
            return self._on_observation(obs)

    def _on_observation(self, obs: Observation) -> List[Alert]:
        cam = obs.camera_id
        self.last_obs[cam] = obs
        for p in obs.people:
            st = self.tracks.setdefault((cam, p.track_id), TrackState())
            st.buffer.add(obs.t, p)
            st.last_t = obs.t
        for key in [k for k, st in self.tracks.items() if k[0] == cam and obs.t - st.last_t > self.forget_s]:
            del self.tracks[key]
        if obs.t < self.next_eval.get(cam, obs.t):
            return []
        self.next_eval[cam] = obs.t + self.hop_s
        out = []
        for (c, tid), st in self.tracks.items():
            if c != cam or obs.t - st.last_t > self.hop_s:
                continue
            f = features(st.buffer.window(obs.t, self.window_s), self.window_s)
            if f is None or f["coverage"] < 0.6:
                continue
            pred = ActionPrediction(camera_id=cam, track_id=tid, t_start=obs.t - self.window_s, t_end=obs.t,
                                    probs=self.classifier.predict_proba(f))
            st.label, st.probs = pred.label, pred.probs
            fw = fuse(pred, self.sync.imu_peak(pred))
            st.fused = fw.model_dump()
            ev = st.engine.step(fw.t_end, fw.p_fall, fw.imu_peak, person=f"P-{tid:03d}", camera_id=cam,
                                zone=self.zones.get(cam, "A"))
            if ev is not None:
                out.append(self._emit(ev))
        return out

    def _emit(self, ev: Event) -> Alert:
        alert = make_alert(ev)
        log.warning("ОПОВЕЩЕНИЕ: %s", alert.text)
        self.alerts.append(alert)
        if self.store is not None:
            self.store.add(ev, alert)
        if self.bus is not None:
            self.bus.publish("cps/alerts", alert.model_dump())
        for cb in self.listeners:
            cb(alert)
        return alert

    def people(self, camera_id: Optional[str] = None) -> List[dict]:
        with self._lock:
            return [{"camera_id": c, "track_id": tid, "person": f"P-{tid:03d}", "action": st.label,
                     "probs": {k: round(v, 3) for k, v in st.probs.items()}, "state": st.engine.state,
                     "last_seen": st.last_t, "fused": st.fused}
                    for (c, tid), st in sorted(self.tracks.items()) if camera_id in (None, c)]

    def labels(self, camera_id: str) -> Tuple[Dict[int, str], set]:
        with self._lock:
            labels = {tid: st.label for (c, tid), st in self.tracks.items() if c == camera_id}
            alarm = {tid for (c, tid), st in self.tracks.items() if c == camera_id and st.engine.state == "ALERT_SENT"}
            return labels, alarm
