"""Золотой прогон «падение → оповещение» на каждом PR, без железа."""
from pathlib import Path

from scripts.eval_gate import check
from src.alerts.generator import render
from src.replay import load, run

REC = Path(__file__).resolve().parents[1] / "eval" / "recordings"


def test_fall_with_imu_gives_one_alert_within_kpi():
    res = run(load(REC / "fall_with_imu.jsonl"))
    assert len(res.alerts) == 1 and res.false_alarms == 0
    assert res.matched[12.0] <= 4.0
    assert "подтвердил" in render(res.alerts[0][1])


def test_without_imu_video_still_alerts():
    res = run(load(REC / "fall_no_imu.jsonl"))
    assert len(res.matched) == 1
    assert "подтверждения датчика нет" in render(res.alerts[0][1])


def test_walking_and_sitting_do_not_alert():
    for name in ("walk_only", "sit_down"):
        assert run(load(REC / f"{name}.jsonl")).alerts == []


def test_gate_catches_regressions():
    base = {"recall": 1.0, "false_alarms": 0, "latency_max_s": 1.5}
    ok = {"recall": 1.0, "false_alarms": 0, "latency_max_s": 1.5}
    assert check(ok, base) == []
    assert check({**ok, "recall": 0.8}, base)
    assert check({**ok, "false_alarms": 1}, base)
    assert check({**ok, "latency_max_s": 4.5}, base)
