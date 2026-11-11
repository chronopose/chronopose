from datetime import datetime, timezone

from scripts.team_metrics import report, summarize

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)
PRS = [
    {"author": {"login": "anna"}, "createdAt": "2026-11-18T10:00:00Z", "mergedAt": "2026-11-18T16:00:00Z",
     "additions": 120, "deletions": 30},
    {"author": {"login": "boris"}, "createdAt": "2026-11-17T10:00:00Z", "mergedAt": "2026-11-19T10:00:00Z",
     "additions": 500, "deletions": 20},
    {"author": {"login": "anna"}, "createdAt": "2026-11-01T10:00:00Z", "mergedAt": "2026-11-02T10:00:00Z",
     "additions": 10, "deletions": 0},  # старше недели — не считается
]


def test_summary_counts_last_week_only():
    m = summarize(PRS, 7, NOW)
    assert m["merged"] == 2
    assert m["median_hours_to_merge"] == 27.0
    assert m["big_prs_over_400"] == 1
    assert m["by_author"] == {"anna": 1, "boris": 1}
    assert "Слито PR" in report(m, 7)


def test_empty_week():
    assert "нет" in report(summarize([], 7, NOW), 7)
