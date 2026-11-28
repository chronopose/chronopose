"""Связывает задачи публичной доски с коммитами из принятой истории Git."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from scripts.claim_role import done_keys

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "docs" / "board"
TASK = re.compile(r"\bSCRUM-[0-9]+\b")


def accepted_commits(ref: str) -> dict[str, str]:
    history = subprocess.check_output(
        ["git", "log", "--encoding=UTF-8", "-z", "--format=%H%x00%B", "--end-of-options", ref, "--"],
        cwd=ROOT,
        encoding="utf-8",
    )
    fields = iter(history.removesuffix("\0").split("\0"))
    return dict(zip(fields, fields))


def sync(issues: list[dict], commits: dict[str, str], reviewed: dict[str, list[str]]) -> list[dict]:
    tasks = {issue["k"] for issue in issues if issue["t"] != "Эпик"}
    links: dict[str, list[str]] = {key: [] for key in tasks}
    done = set()
    for sha, message in commits.items():
        closed = set(done_keys(message)) & tasks
        subject, _, body = message.partition("\n")
        mentioned = set(TASK.findall(subject))
        if subject.startswith("Merge pull request #"):
            mentioned.update(TASK.findall(body.lstrip().partition("\n")[0]))
        done.update(closed)
        for key in closed | (mentioned & tasks):
            links[key].append(sha)

    for sha, keys in reviewed.items():
        if sha not in commits:
            raise ValueError(f"Коммит из списка проверенных задач отсутствует в принятой истории: {sha}")
        for key in keys:
            if key not in tasks:
                raise ValueError(f"Задачи из списка проверенных нет на доске: {key}")
            done.add(key)
            if sha not in links[key]:
                links[key].append(sha)

    result = []
    for issue in issues:
        key = issue["k"]
        card = issue.copy()
        if key in done:
            card.update(c="done", st="Готово")
        if links.get(key):
            card["commits"] = links[key]
        result.append(card)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="main", help="принятая ветка или её коммит")
    parser.add_argument("--output", required=True, type=Path, help="путь к issues.json для публикации")
    args = parser.parse_args()
    issues = json.loads((BOARD / "issues.json").read_text(encoding="utf-8"))
    reviewed = json.loads((BOARD / "reviewed.json").read_text(encoding="utf-8"))
    cards = sync(issues, accepted_commits(args.ref), reviewed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Готово задач: {sum(card['t'] != 'Эпик' and card['c'] == 'done' for card in cards)}")


if __name__ == "__main__":
    main()
