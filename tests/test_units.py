"""Модульные тесты блоков MVP: шина, IMU, слияние, классификатор, трекинг, хранилище."""
import pytest

from src.alerts.generator import make_alert
from src.bus import InMemoryBus, topic_matches
from src.contracts import ActionPrediction, Event, ImuSample, PersonPose
from src.fusion.late import fuse
from src.fusion.sync import WindowSync
from src.iot.receiver import ImuReceiver
from src.iot.simulator import samples
from src.models.classifier import RuleClassifier
from src.models.preprocess import SkeletonBuffer, features, mask_missing, normalize
from src.storage import Store
from src.vision.pose import IouTracker
from src.vision.synthetic import Actor, SyntheticScene


def test_topic_wildcards():
    assert topic_matches("cps/imu/+/telemetry", "cps/imu/imu_001/telemetry")
    assert not topic_matches("cps/imu/+/telemetry", "cps/imu/imu_001/status")
    assert topic_matches("cps/#", "cps/alerts")
    bus, got = InMemoryBus(), []
    bus.subscribe("cps/alerts", lambda t, p: got.append(p))
    bus.publish("cps/alerts", {"x": 1})
    bus.publish("cps/other", {"x": 2})
    assert got == [{"x": 1}]


@pytest.mark.parametrize("with_g", [True, False])
def test_imu_impact_detected_with_and_without_gravity(with_g):
    rec = ImuReceiver(clock=lambda: 100.0)
    for s in samples(t0=90.0, duration=10, fall_at=6.0, with_g=with_g):
        rec.add(s)
    assert rec.impact("imu_001", 90.0 + 5.5, 90.0 + 7.0) is True    # окно с падением
    assert rec.impact("imu_001", 90.0 + 1.0, 90.0 + 3.0) is False   # обычная ходьба
    assert rec.impact("imu_001", 200.0, 202.0) is None               # данных нет
    assert rec.impact("unknown", 95.0, 97.0) is None


def test_imu_status_online_and_bad_payload_ignored():
    bus = InMemoryBus()
    rec = ImuReceiver(bus, clock=lambda: 10.5)
    bus.publish("cps/imu/imu_001/telemetry", {"garbage": True})
    s = ImuSample(device_id="imu_001", sequence=1, t_phone=0, t_server=10.0, acc=(0, 0, 9.8))
    bus.publish("cps/imu/imu_001/telemetry", s.model_dump())
    bus.publish("cps/imu/imu_001/status", {"ok": False, "error": "нет связи с телефоном"})
    st = rec.status()["imu_001"]
    assert st["online"] and st["samples"] == 1 and st["error"] == "нет связи с телефоном"


def pred(p_fall: float, cam: str = "cam_01") -> ActionPrediction:
    return ActionPrediction(camera_id=cam, track_id=1, t_start=8.0, t_end=10.0,
                            probs={"stand": 0, "walk": 0, "fall": p_fall, "lie": 1 - p_fall})


def test_fusion_flags_and_boost():
    assert fuse(pred(0.5), True).p_fall == pytest.approx(0.65)
    assert fuse(pred(0.5), False).p_fall == 0.5          # отсутствие удара не снижает
    none = fuse(pred(0.5), None)
    assert none.sources == {"video": True, "imu": False} and none.p_fall == 0.5
    assert fuse(pred(0.1), True).p_fall == 0.1           # удар без падения на видео не поднимает


def test_sync_uses_only_devices_of_camera():
    rec = ImuReceiver(clock=lambda: 20.0)
    for s in samples(t0=0.0, duration=12, fall_at=9.0):
        rec.add(s)
    sync = WindowSync(rec, {"imu_001": "cam_01"})
    assert sync.imu_peak(pred(0.9, "cam_01")) is True
    assert sync.imu_peak(pred(0.9, "cam_02")) is None
    assert WindowSync(None, {}).imu_peak(pred(0.9)) is None


def scene_features(actor: Actor, t: float):
    sc, buf = SyntheticScene([actor]), SkeletonBuffer()
    for obs in sc.frames(t + 0.01, fps=15):
        buf.add(obs.t, obs.people[0])
    return features(buf.window(t))


def test_classifier_on_synthetic_motion():
    clf = RuleClassifier()
    walk = clf.predict_proba(scene_features(Actor(1, 100, 40.0), 4.0))
    stand = clf.predict_proba(scene_features(Actor(1, 300, 0.0), 4.0))
    fall = clf.predict_proba(scene_features(Actor(1, 100, 40.0, fall_at=3.0), 4.0))
    lie = clf.predict_proba(scene_features(Actor(1, 100, 40.0, fall_at=3.0), 7.0))
    assert max(walk, key=walk.get) == "walk"
    assert max(stand, key=stand.get) == "stand"
    assert fall["fall"] > 0.9
    assert max(lie, key=lie.get) == "lie" and lie["fall"] < 0.1
    assert abs(sum(fall.values()) - 1) < 1e-6


def test_missing_keypoints_masked_and_normalized():
    kps = [(100.0, 100.0 + i * 10, 0.9) for i in range(17)]
    kps[3] = (1.0, 1.0, 0.1)
    a = mask_missing(kps)
    assert a[3, 0] != a[3, 0]  # NaN
    n = normalize(a)
    assert abs(n[11, 1] + n[12, 1]) < 1e-6 or n[11, 1] == n[11, 1]
    assert features([]) is None


def person(x: float, tid: int = -1) -> PersonPose:
    return PersonPose(track_id=tid, bbox=(x, 100, x + 80, 300), keypoints=[(x, 100, 0.9)] * 17)


def test_iou_tracker_keeps_ids():
    tr = IouTracker()
    a = tr.update([person(0), person(400)])
    b = tr.update([person(410), person(8)])
    assert {p.track_id for p in a} == {1, 2}
    assert b[0].track_id == a[1].track_id and b[1].track_id == a[0].track_id
    c = tr.update([person(800)])
    assert c[0].track_id == 3


def test_store_roundtrip():
    st = Store("sqlite:///:memory:")
    ev = Event(t_start=1.0, t_confirmed=2.0, confidence=0.9, imu_confirmed=None)
    st.add(ev, make_alert(ev))
    rows = st.list()
    assert rows[0]["id"] == ev.id and rows[0]["imu_confirmed"] is None
    assert st.get(ev.id)["confidence"] == 0.9 and st.get("missing") is None
