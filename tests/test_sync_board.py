import pytest

from scripts.sync_board import sync


def task(key, status="new", kind="Задача"):
    return {"k": key, "t": kind, "c": status, "st": "К выполнению"}


def test_links_accepted_commits_and_only_closes_confirmed_tasks():
    issues = [task("SCRUM-4"), task("SCRUM-7"), task("SCRUM-25", "done"), task("SCRUM-1", kind="Эпик")]
    commits = {
        "merge": "Merge pull request #16 from teammate/fix-ci\n\nSCRUM-4: исправить CI",
        "part": "SCRUM-7: частичная правка; см. SCRUM-4\n\nСм. SCRUM-25",
        "done": "Исправить CI\n\nTask-Done: SCRUM-4, SCRUM-1, SCRUM-99",
    }

    cards = sync(issues, commits, {"part": ["SCRUM-4"]})

    assert cards[0] == {**issues[0], "c": "done", "st": "Готово", "commits": ["merge", "part", "done"]}
    assert cards[1] == {**issues[1], "commits": ["part"]}
    assert cards[2:] == issues[2:]
    assert issues[0]["c"] == "new"


def test_reviewed_task_closes_without_trailer_and_requires_accepted_commit():
    issues = [task("SCRUM-4")]
    assert sync(issues, {"old": "Добавить CI"}, {"old": ["SCRUM-4"]}) == [
        {**issues[0], "c": "done", "st": "Готово", "commits": ["old"]},
    ]
    with pytest.raises(ValueError, match="unmerged"):
        sync(issues, {}, {"unmerged": ["SCRUM-4"]})
