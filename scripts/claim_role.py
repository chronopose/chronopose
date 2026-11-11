"""Захват ролей по коммитам.

Правило проекта: роль достаётся тому, кто первым закрыл задачу этой роли.
Задача считается закрытой, если в сообщении коммита есть строка
    Task-Done: SCRUM-123
Роль задачи берётся из .github/roles/task_roles.json (ключ Jira → роль).
Состояние ролей хранится в .github/roles/roles.json, таблица для людей — ROLES.md.

Запуск в GitHub Actions: python scripts/claim_role.py --event "$GITHUB_EVENT_PATH"
Локальная проверка:      python scripts/claim_role.py --message "..." --author login
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_ROLES = ROOT / ".github" / "roles" / "task_roles.json"
ROLES_STATE = ROOT / ".github" / "roles" / "roles.json"
ROLES_MD = ROOT / "ROLES.md"
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"

# Какие папки ревьюит владелец роли. Пока роль свободна, строка закомментирована.
ROLE_PATHS = {
    "DM": ["*", "/docs/", "/.github/", "/src/events/", "/src/fusion/"],
    "CV": ["/src/vision/", "/src/tracking/"],
    "ML": ["/src/models/", "/eval/", "/scripts/eval_gate.py"],
    "IoT": ["/src/iot/", "/firmware/"],
    "WEB": ["/src/api/", "/web/"],
}

DONE_RE = re.compile(r"^\s*Task-Done:\s*((?:[A-Z][A-Z0-9]+-\d+)(?:\s*,\s*[A-Z][A-Z0-9]+-\d+)*)\s*$", re.MULTILINE)

ROLE_TITLES = {
    "DM": "Dungeon Master — руководитель, архитектура, слияние и события",
    "CV": "Инженер зрения — камеры, поза, трекинг",
    "ML": "Исследователь моделей — классификация, данные, эксперименты",
    "IoT": "Инженер датчиков — телефоны-IMU, MQTT, ESP32",
    "WEB": "Веб-разработчик — сайт, API, демо-панель, деплой",
}


def done_keys(message: str) -> list[str]:
    keys: list[str] = []
    for m in DONE_RE.finditer(message):
        keys += [k.strip() for k in m.group(1).split(",")]
    return keys


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_commit(state: dict, task_roles: dict, message: str, author: str, sha: str, today: str) -> list[str]:
    """Обновляет state; возвращает строки журнала."""
    log: list[str] = []
    for key in done_keys(message):
        role = task_roles.get(key)
        if role is None:
            log.append(f"{key}: задачи нет в task_roles.json — пропуск")
            continue
        slot = state["roles"][role]
        if slot["owner"] is None:
            slot.update(owner=author, task=key, commit=sha[:7], date=today)
            log.append(f"{key}: роль {role} закреплена за @{author}")
        elif slot["owner"] == author:
            log.append(f"{key}: @{author} уже владеет ролью {role}")
        else:
            log.append(f"{key}: роль {role} уже у @{slot['owner']} — @{author} помогает как участник")
        state.setdefault("done", {})[key] = {"by": author, "commit": sha[:7], "date": today}
    return log


def render_md(state: dict) -> str:
    rows = ["| Роль | Зона | Владелец | Задача | Коммит | Дата |", "| --- | --- | --- | --- | --- | --- |"]
    for role, slot in state["roles"].items():
        owner = f"@{slot['owner']}" if slot["owner"] else "свободна"
        cells = [role, ROLE_TITLES[role], owner, slot["task"] or "—", slot["commit"] or "—", slot["date"] or "—"]
        rows.append("| " + " | ".join(cells) + " |")
    return (
        "# Роли в команде\n\n"
        "Роль получает тот, кто **первым закрыл задачу этой роли** из Jira.\n"
        "Чтобы закрыть задачу, добавьте в сообщение коммита строку `Task-Done: SCRUM-123`.\n"
        "Таблицу обновляет GitHub Actions после пуша в `main` — руками её не правим.\n\n"
        + "\n".join(rows)
        + f"\n\nЗакрыто задач: {len(state.get('done', {}))}.\n"
    )


def render_codeowners(state: dict) -> str:
    """CODEOWNERS из таблицы ролей: GitHub сам зовёт владельца роли на ревью PR."""
    lines = ["# Генерируется scripts/claim_role.py — руками не править.",
             "# Последнее совпадение важнее, поэтому общее правило «*» идёт первым."]
    for role, paths in ROLE_PATHS.items():
        owner = state["roles"][role]["owner"]
        for path in paths:
            lines.append(f"{path} @{owner}" if owner else f"# {path} — роль {role} свободна")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--event", help="путь к JSON события push из GitHub Actions")
    p.add_argument("--message")
    p.add_argument("--author")
    p.add_argument("--sha", default="local00")
    a = p.parse_args(argv)

    task_roles, state = load(TASK_ROLES), load(ROLES_STATE)
    today = date.today().isoformat()
    commits = []
    if a.event:
        ev = json.loads(Path(a.event).read_text(encoding="utf-8"))
        for c in ev.get("commits", []):
            login = (c.get("author") or {}).get("username") or (c.get("author") or {}).get("name", "unknown")
            commits.append((c.get("message", ""), login, c.get("id", "")))
    elif a.message and a.author:
        commits.append((a.message, a.author, a.sha))
    else:
        p.error("нужен --event или --message вместе с --author")

    log: list[str] = []
    for msg, author, sha in commits:
        log += apply_commit(state, task_roles, msg, author, sha, today)
    ROLES_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ROLES_MD.write_text(render_md(state), encoding="utf-8")
    CODEOWNERS.write_text(render_codeowners(state), encoding="utf-8")
    print("\n".join(log) or "Строк Task-Done не найдено")
    return 0


if __name__ == "__main__":
    sys.exit(main())
