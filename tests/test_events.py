from src.alerts.generator import render
from src.events.engine import FallEngine


def test_single_alert_per_fall_and_recovery():
    eng = FallEngine()
    seq = [0.1, 0.8, 0.9, 0.95, 0.9, 0.1, 0.1, 0.1, 0.1, 0.9, 0.9, 0.9]
    events = [eng.step(t, p, imu_peak=False) for t, p in enumerate(seq)]
    fired = [e for e in events if e]
    assert len(fired) == 2          # одно событие на каждое падение, без дублей
    assert fired[0].t_start == 1


def test_imu_confirms_faster():
    eng = FallEngine()
    assert eng.step(0, 0.9, imu_peak=True) is None
    ev = eng.step(1, 0.9, imu_peak=True)
    assert ev is not None and ev.imu_confirmed


def test_text_has_only_event_fields():
    eng = FallEngine()
    ev = [eng.step(t, 0.9, True) for t in range(2)][-1]
    text = render(ev)
    assert "P-001" in text and "90 %" in text and "подтвердил" in text
