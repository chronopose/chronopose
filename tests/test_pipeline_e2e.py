"""Сквозной прогон MVP без железа: синтетическая камера + синтетический телефон-IMU → оповещение."""
from src.bus import InMemoryBus
from src.iot.receiver import ImuReceiver
from src.iot.simulator import samples
from src.pipeline import Pipeline
from src.storage import Store
from src.vision.synthetic import demo_scene

T0 = 1_800_000_000.0
FALL_AT = 6.0


def run(with_imu: bool):
    bus = InMemoryBus()
    imu = ImuReceiver(bus, clock=lambda: T0 + 30)
    got = []
    bus.subscribe("cps/alerts", lambda topic, p: got.append(p))
    store = Store("sqlite:///:memory:")
    pipe = Pipeline(bus=bus, store=store, imu=imu, devices={"imu_001": "cam_01"})
    if with_imu:
        for s in samples("imu_001", t0=T0, duration=14, fall_at=FALL_AT + 0.3):
            bus.publish("cps/imu/imu_001/telemetry", s.model_dump())
    for obs in demo_scene(t0=T0, fall_at=FALL_AT).frames(14, fps=15):
        pipe.on_observation(obs)
    return got, store, pipe


def test_fall_with_imu_alerts_once_within_kpi():
    got, store, pipe = run(with_imu=True)
    assert len(got) == 1, got                       # одно оповещение, второй человек не тревожит
    a = got[0]
    assert a["person"] == "P-001" and a["imu_confirmed"] is True
    assert a["t"] - (T0 + FALL_AT) <= 4.0           # KPI: не дольше 4 с от начала падения
    assert "подтвердил удар" in a["text"]
    assert store.list()[0]["id"] == a["event_id"]
    assert {p["person"]: p["action"] for p in pipe.people()}["P-001"] == "lie"


def test_without_imu_video_alone_alerts():
    got, _, _ = run(with_imu=False)
    assert len(got) == 1 and got[0]["imu_confirmed"] is None
    assert "подтверждения датчика нет" in got[0]["text"]


def test_imu_confirms_faster_than_video_alone():
    with_imu, _, _ = run(True)
    without, _, _ = run(False)
    assert with_imu[0]["t"] < without[0]["t"]
