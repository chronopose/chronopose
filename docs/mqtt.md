# Топики MQTT

Брокер — Mosquitto на ноутбуке команды (`infra/mosquitto`), порт 1883, вход по логину и паролю.
Изменение топика или формата сообщения — только через ADR.

| Топик | Кто пишет | Кто читает | Сообщение | QoS |
| --- | --- | --- | --- | --- |
| `cps/imu/{device_id}/telemetry` | мост телефона (`src/iot/phone_imu_bridge.py`) | `src/iot/receiver.py` | `ImuSample`: `device_id, sequence, t_phone, t_server, acc[3], gyro[3]` | 0 |
| `cps/imu/{device_id}/status` | мост телефона | приёмник, API | `{"ok": true/false, "error": "..."}` | 1 |
| `cps/alerts` | конвейер (`src/pipeline.py`) | ESP32, демо-панель | `Alert`: `event_id, t, text, person, camera_id, zone, confidence, imu_confirmed` | 1 |
| `cps/actuators/{id}/status` | ESP32 | API | `online` (retain) | 1 |
| `cps/actuators/{id}/ack` | ESP32 | API | `alarm` | 1 |

Время: `t_server` — время ноутбука при приёме (по нему синхронизируем с видео), `t_phone` — время телефона, только для отладки.

Ускорение `acc` — м/с². phyphox отдаёт либо «с учётом g» (около 9,8 в покое), либо «без g» (около 0). Приёмник работает с обоими: удар ищется как отклонение модуля ускорения от медианы окна.
