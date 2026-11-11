"""Метрики команды за неделю по слитым PR: сколько, как быстро, какого размера.

Вход — JSON из `gh pr list --state merged --json number,author,createdAt,mergedAt,additions,deletions`.
    gh pr list --state merged --limit 200 --json number,author,createdAt,mergedAt,additions,deletions > prs.json
    python scripts/team_metrics.py prs.json --days 7
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))  # Python 3.9 не понимает суффикс Z


def summarize(prs: list[dict], days: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    recent = [p for p in prs if p.get("mergedAt") and ts(p["mergedAt"]) >= now - timedelta(days=days)]
    if not recent:
        return {"merged": 0}
    hours = [(ts(p["mergedAt"]) - ts(p["createdAt"])).total_seconds() / 3600 for p in recent]
    sizes = [p["additions"] + p["deletions"] for p in recent]
    by_author: dict[str, int] = {}
    for p in recent:
        login = (p.get("author") or {}).get("login", "?")
        by_author[login] = by_author.get(login, 0) + 1
    return {
        "merged": len(recent),
        "median_hours_to_merge": round(median(hours), 1),
        "median_pr_size": int(median(sizes)),
        "big_prs_over_400": sum(s > 400 for s in sizes),
        "by_author": dict(sorted(by_author.items(), key=lambda kv: -kv[1])),
    }


def ci_health(runs: list[dict], days: int, now: datetime | None = None) -> dict:
    """Доля упавших запусков CI за период. Вход — `gh run list --workflow ci --json conclusion,createdAt`."""
    now = now or datetime.now(timezone.utc)
    recent = [r for r in runs if r.get("conclusion") and ts(r["createdAt"]) >= now - timedelta(days=days)]
    failed = sum(r["conclusion"] == "failure" for r in recent)
    return {"runs": len(recent), "failed": failed, "fail_rate": round(failed / len(recent), 2) if recent else 0.0}


def report(m: dict, days: int, ci: dict | None = None) -> str:
    ci_line = ""
    if ci and ci["runs"]:
        pct = round(ci["fail_rate"] * 100)
        ci_line = f"CI: {ci['runs']} запусков, упало {ci['failed']} ({pct} %). Цель — меньше 10 %.\n"
    if not m["merged"]:
        return f"## Метрики команды за {days} дн.\n\nСлитых PR нет.\n\n{ci_line}"
    authors = ", ".join(f"@{a}: {n}" for a, n in m["by_author"].items())
    return (f"## Метрики команды за {days} дн.\n\n"
            f"| Слито PR | Медиана до слияния | Медианный размер | PR > 400 строк |\n| --- | --- | --- | --- |\n"
            f"| {m['merged']} | {m['median_hours_to_merge']} ч | {m['median_pr_size']} строк "
            f"| {m['big_prs_over_400']} |\n\n"
            f"По авторам: {authors}\n\n{ci_line}\nЦели: медиана до слияния < 24 ч, размер < 300 строк.\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("prs_json")
    p.add_argument("--runs", help="JSON из gh run list --workflow ci --json conclusion,createdAt")
    p.add_argument("--days", type=int, default=7)
    a = p.parse_args(argv)
    ci = ci_health(json.loads(Path(a.runs).read_text(encoding="utf-8")), a.days) if a.runs else None
    text = report(summarize(json.loads(Path(a.prs_json).read_text(encoding="utf-8")), a.days), a.days, ci)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
