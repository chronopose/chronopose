import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from claim_role import apply_commit, done_keys

TASKS = {"SCRUM-31": "CV", "SCRUM-33": "CV", "SCRUM-46": "IoT"}


def empty_state():
    return {"roles": {r: {"owner": None, "task": None, "commit": None, "date": None}
                      for r in ["DM", "CV", "ML", "IoT", "WEB"]}, "done": {}}


def test_parses_one_or_many_keys():
    assert done_keys("feat: поза\n\nTask-Done: SCRUM-31") == ["SCRUM-31"]
    assert done_keys("x\nTask-Done: SCRUM-31, SCRUM-33\n") == ["SCRUM-31", "SCRUM-33"]
    assert done_keys("SCRUM-31: упоминание без строки Task-Done") == []


def test_first_finisher_takes_role():
    st = empty_state()
    apply_commit(st, TASKS, "Task-Done: SCRUM-31", "anna", "abc1234567", "2026-11-12")
    apply_commit(st, TASKS, "Task-Done: SCRUM-33", "boris", "def1234567", "2026-11-13")
    assert st["roles"]["CV"]["owner"] == "anna"
    assert st["roles"]["CV"]["task"] == "SCRUM-31"
    assert set(st["done"]) == {"SCRUM-31", "SCRUM-33"}


def test_unknown_key_is_ignored():
    st = empty_state()
    log = apply_commit(st, TASKS, "Task-Done: SCRUM-999", "anna", "abc", "2026-11-12")
    assert all(v["owner"] is None for v in st["roles"].values())
    assert "пропуск" in log[0]
