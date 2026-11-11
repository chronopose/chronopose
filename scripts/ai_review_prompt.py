"""ИИ-ревью без платного API: собирает изменения ветки и правила проекта в один запрос.

    python scripts/ai_review_prompt.py            # сравнить с origin/main, записать ai-review.md
    python scripts/ai_review_prompt.py --base main

Файл ai-review.md вставьте целиком в любой ИИ-чат (бесплатный тоже подходит)
или скажите Claude Code «проведи ревью по ai-review.md». Замечания по делу — в PR.
Файл в git не попадает.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_DIFF_CHARS = 60_000  # больше бесплатный чат обычно не примет — значит, PR пора резать

CHECKLIST = """\
Проверь изменения как строгий ревьюер команды. Ответь по-русски, списком, самое важное первым.
1. Ошибки логики и граничные случаи (пустые данные, датчик молчит, два падения подряд).
2. Не сломан ли контракт: топики MQTT, формат события, формат записей JSONL.
3. Есть ли тесты на новое поведение; что стоит добавить.
4. Нарушения правил проекта ниже (железо без закупок, приватность, стиль).
5. Что можно упростить.
Не пересказывай код и не хвали — только замечания с указанием файла и строки."""


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8")


def build(base: str) -> str:
    rules = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    log = git("log", "--oneline", f"{base}..HEAD")
    stat = git("diff", "--stat", f"{base}...HEAD")
    diff = git("diff", f"{base}...HEAD")
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n… [обрезано: PR слишком большой для одного ревью — разрежьте его]\n"
    return (f"{CHECKLIST}\n\n## Правила проекта\n\n{rules}\n\n## Коммиты\n\n```\n{log}```\n\n"
            f"## Файлы\n\n```\n{stat}```\n\n## Изменения\n\n```diff\n{diff}```\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="origin/main")
    p.add_argument("--out", default="ai-review.md")
    a = p.parse_args(argv)
    text = build(a.base)
    (ROOT / a.out).write_text(text, encoding="utf-8")
    print(f"Готово: {a.out}, {len(text)} символов. Вставьте его в ИИ-чат целиком.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
