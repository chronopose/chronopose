#!/bin/sh
# Создаёт infra/mosquitto/passwd с тремя пользователями. Пароли — из переменных окружения.
# MQTT_PASSWORD=... PHONE_PASSWORD=... ESP32_PASSWORD=... sh infra/mosquitto/make_passwd.sh
set -e
cd "$(dirname "$0")"
: > passwd
docker run --rm -v "$PWD:/m" eclipse-mosquitto:2 sh -c "
  mosquitto_passwd -b /m/passwd server '${MQTT_PASSWORD:?нужен MQTT_PASSWORD}' &&
  mosquitto_passwd -b /m/passwd phone '${PHONE_PASSWORD:?нужен PHONE_PASSWORD}' &&
  mosquitto_passwd -b /m/passwd esp32 '${ESP32_PASSWORD:?нужен ESP32_PASSWORD}'"
echo "Готово: infra/mosquitto/passwd (в git не попадает)"
