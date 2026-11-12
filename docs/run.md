# Как запустить MVP

## 1. Демо без железа — за 2 минуты

```bash
python -m venv .venv && .venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m src.app --synthetic --port 8000
```

Откройте http://localhost:8000. Синтетическая камера показывает двух людей; каждые 20 секунд один падает на 6-й секунде,
синтетический телефон фиксирует удар, на пульте появляется оповещение. MQTT и база не нужны (журнал — `data/chronopose.db`).

> На Windows порт 8000 иногда занят системой — возьмите `--port 8077`.

## 2. Реальная система — телефоны, ESP32, ноутбук

| Шаг | Что сделать |
| --- | --- |
| Сеть | Все устройства в одной Wi-Fi сети (можно точка доступа с телефона). Узнайте IP ноутбука. |
| Брокер | `cp .env.example .env`, задайте пароли, `sh infra/mosquitto/make_passwd.sh`, затем `docker compose up -d mqtt db` |
| Телефон-камера | Приложение IP Webcam → «Запустить» → адрес вида `http://192.168.1.21:8080/video` |
| Телефон-IMU | phyphox → эксперимент с акселерометром → «Разрешить удалённый доступ». На ноутбуке: `MQTT_USER=phone MQTT_PASSWORD=… python -m src.iot.phone_imu_bridge --phone <ip телефона> --broker localhost` |
| ESP32 | В `firmware/esp32_alarm/esp32_alarm.ino` впишите Wi-Fi, IP ноутбука и пароль `esp32`, прошейте из Arduino IDE |
| Сервер | `pip install -r requirements-vision.txt`, затем `MQTT_USER=server MQTT_PASSWORD=… python -m src.app --camera http://192.168.1.21:8080/video --mqtt localhost --device imu_001` |

Первый запуск скачает модель YOLO26n-pose. На CPU ноутбука ждите 8–15 кадров в секунду при 640×480.

Проверка по шагам:

1. `GET /api/cameras` — `connected: true`, `fps` больше 8.
2. `GET /api/sensors` — у `imu_001` `online: true`, частота 50–100 Гц.
3. Пройдите перед камерой — на пульте «идёт».
4. Сядьте на стул — тревоги нет.
5. Упадите на мат — оповещение меньше чем через 4 секунды, ESP32 мигает 10 секунд.

## 3. Всё в Docker

```bash
docker compose up --build            # синтетика через настоящий Mosquitto и PostgreSQL
VISION=1 APP_ARGS="--camera http://192.168.1.21:8080/video --mqtt mqtt" docker compose up --build
```

## 4. Без телефона-IMU, но с реальным MQTT

```bash
python -m src.iot.simulator --broker localhost --fall-at 6
```

## Что где

| Модуль | Задача | Файл |
| --- | --- | --- |
| Контракты | SCRUM-6 | `src/contracts.py` |
| Захват видео | SCRUM-30 | `src/vision/capture.py` |
| Поза + ByteTrack | SCRUM-31, 33 | `src/vision/pose.py` |
| Предобработка, окна 2 с | SCRUM-39 | `src/models/preprocess.py` |
| Классификатор | SCRUM-40 | `src/models/classifier.py` |
| Мост телефона, приёмник | SCRUM-47, 49 | `src/iot/phone_imu_bridge.py`, `src/iot/receiver.py` |
| Mosquitto | SCRUM-48 | `infra/mosquitto/`, `docs/mqtt.md` |
| Синхронизация и слияние | SCRUM-53, 54 | `src/fusion/` |
| События и оповещения | SCRUM-56, 57 | `src/events/engine.py`, `src/alerts/generator.py` |
| API, WebSocket, пульт | SCRUM-76…79 | `src/api/app.py`, `web/index.html` |
| ESP32 | SCRUM-85 | `firmware/esp32_alarm/` |
| Сквозной конвейер | SCRUM-86 | `src/pipeline.py`, `src/app.py`, `tests/test_pipeline_e2e.py` |
| Docker, CI | SCRUM-4, 7 | `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml` |
