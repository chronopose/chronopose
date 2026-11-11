// ESP32 как исполнитель (SCRUM-85): подписка на cps/alerts, мигание светодиодом при тревоге.
// Библиотека: PubSubClient (Arduino Library Manager). Плата: ESP32 Dev Module.
// Встроенный светодиод на многих платах DevKit — GPIO 2; на вашей плате может быть другим.

#include <WiFi.h>
#include <PubSubClient.h>

const char* WIFI_SSID = "YOUR_WIFI";       // заполнить локально, не коммитить
const char* WIFI_PASS = "YOUR_PASSWORD";
const char* MQTT_HOST = "192.168.1.10";    // ноутбук с Mosquitto
const int   LED_PIN   = 2;

WiFiClient net;
PubSubClient mqtt(net);
unsigned long alarmUntil = 0;

void onMessage(char* topic, byte* payload, unsigned int len) {
  alarmUntil = millis() + 10000;           // 10 секунд мигания на каждое событие
  mqtt.publish("cps/actuators/esp32_01/ack", "alarm", false);
}

void reconnect() {
  while (!mqtt.connected()) {
    if (mqtt.connect("esp32_01")) {
      mqtt.subscribe("cps/alerts");
      mqtt.publish("cps/actuators/esp32_01/status", "online", true);
    } else {
      delay(2000);
    }
  }
}

void setup() {
  pinMode(LED_PIN, OUTPUT);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) delay(300);
  mqtt.setServer(MQTT_HOST, 1883);
  mqtt.setCallback(onMessage);
}

void loop() {
  if (!mqtt.connected()) reconnect();
  mqtt.loop();
  bool on = millis() < alarmUntil && (millis() / 200) % 2 == 0;
  digitalWrite(LED_PIN, on ? HIGH : LOW);
}
