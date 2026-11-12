# chronopose

Студенческий НИП: детекция ключевых точек и классификация поведения человека в киберфизической системе.
Видим позу → понимаем действие → оповещаем словами.

- **Цель ближайшая:** MVP к 1 декабря 2026 — см. [docs/mvp.md](docs/mvp.md).
- **Задачи:** Jira, проект SCRUM на chronopose.atlassian.net. Публичная копия доски — [chronopose.github.io/chronopose/board](https://chronopose.github.io/chronopose/board/) (снимок, файлы в `docs/board/`).
- **Презентация:** [chronopose.github.io/chronopose/slides](https://chronopose.github.io/chronopose/slides/) — светлая и неоновая версии, исходники в `docs/slides/`.
- **Роли:** [ROLES.md](ROLES.md) — заполняется автоматически.
- **Железо:** только то, что есть — Android-смартфоны и одна ESP32.
- **Как работаем:** [docs/process.md](docs/process.md) — PR, ревью, гейт качества, релизы. Цели — [docs/okr.md](docs/okr.md), решения — [docs/adr/](docs/adr/).

## Быстрый старт

```bash
pip install -r requirements-dev.txt
python -m src.app --synthetic          # пульт на http://localhost:8000, железо не нужно
```

Реальная система с телефонами и ESP32 — [docs/run.md](docs/run.md).

## Как взять роль

Роли пока не распределены. **Кто первым закроет задачу роли, тот её и забирает.**

1. Возьмите задачу в Jira (метки `role-cv`, `role-ml`, `role-iot`, `role-web`, `role-dm` подсказывают роль).
2. Работайте в ветке `feat/SCRUM-31-pose`.
3. В последнем коммите задачи добавьте строку:

   ```
   SCRUM-31: обёртка над YOLO-pose

   Task-Done: SCRUM-31
   ```

4. После слияния в `main` workflow `claim-role` впишет вас в [ROLES.md](ROLES.md), если роль была свободна.

Дальше роль ваша, но задачи других ролей брать можно — это засчитывается как помощь.
Важно: GitHub должен узнавать автора коммита — укажите в `git config user.email` почту из своего аккаунта GitHub.

## Структура

```
src/          код системы (events, alerts, iot, replay)
firmware/     скетч ESP32
eval/         записи для прогона и база метрик
scripts/      роли, гейт качества, метрики команды
docs/         MVP, процесс, OKR, ADR, шаблоны (дизайн, статус, постмортем, карточка модели)
tests/        pytest
.github/      CI и захват ролей
```

## Локально

```bash
pip install -r requirements-dev.txt
pre-commit install               # проверки перед каждым коммитом
ruff check .
pytest -q
python scripts/eval_gate.py      # качество на записях: полнота, ложные тревоги, задержка
python -m src.replay eval/recordings/fall_with_imu.jsonl   # прогон «падение → оповещение» без железа
```
