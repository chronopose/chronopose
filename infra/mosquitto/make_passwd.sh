#!/bin/sh
# Создаёт infra/mosquitto/passwd с тремя пользователями. Пароли — из переменных окружения.
# MQTT_PASSWORD=... PHONE_PASSWORD=... ESP32_PASSWORD=... sh infra/mosquitto/make_passwd.sh
#!/bin/bash
# Создаёт passwd-файл с пользователями: server, phone, esp32
docker run --rm eclipse-mosquitto:2 mosquitto_passwd -c -b /mosquitto/config/passwd server "secret_server"
docker run --rm eclipse-mosquitto:2 mosquitto_passwd -b /mosquitto/config/passwd phone "secret_phone"
docker run --rm eclipse-mosquitto:2 mosquitto_passwd -b /mosquitto/config/passwd esp32 "secret_esp32"
