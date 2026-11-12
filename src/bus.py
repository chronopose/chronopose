"""Шина сообщений: MQTT в системе, память — в тестах и демо без брокера.

Схема топиков — docs/mqtt.md. Подписка поддерживает шаблоны MQTT: + (один уровень) и # (хвост).
"""
from __future__ import annotations

import json
import os
import threading
from typing import Callable, Dict, List, Tuple

Handler = Callable[[str, dict], None]


def topic_matches(pattern: str, topic: str) -> bool:
    p, t = pattern.split("/"), topic.split("/")
    for i, part in enumerate(p):
        if part == "#":
            return True
        if i >= len(t) or (part != "+" and part != t[i]):
            return False
    return len(p) == len(t)


class InMemoryBus:
    """Синхронная шина в памяти: publish сразу вызывает подписчиков."""

    def __init__(self) -> None:
        self._subs: List[Tuple[str, Handler]] = []
        self._lock = threading.Lock()
        self.published: List[Tuple[str, dict]] = []

    def subscribe(self, pattern: str, handler: Handler) -> None:
        with self._lock:
            self._subs.append((pattern, handler))

    def publish(self, topic: str, payload: dict, retain: bool = False) -> None:
        self.published.append((topic, payload))
        with self._lock:
            subs = list(self._subs)
        for pattern, handler in subs:
            if topic_matches(pattern, topic):
                handler(topic, payload)

    def close(self) -> None:
        pass


class MqttBus:
    """paho-mqtt (Callback API v2). Логин и пароль — из MQTT_USER / MQTT_PASSWORD."""

    def __init__(self, host: str = "localhost", port: int = 1883, client_id: str = "chronopose") -> None:
        import paho.mqtt.client as mqtt

        self._handlers: Dict[str, List[Handler]] = {}
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        user = os.environ.get("MQTT_USER")
        if user:
            self.client.username_pw_set(user, os.environ.get("MQTT_PASSWORD"))
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        self.client.connect_async(host, port, keepalive=30)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        for pattern in self._handlers:  # после переподключения подписки восстанавливаются
            client.subscribe(pattern, qos=1)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {"raw": msg.payload.decode("utf-8", "replace")}
        for pattern, handlers in list(self._handlers.items()):
            if topic_matches(pattern, msg.topic):
                for h in handlers:
                    h(msg.topic, payload)

    def subscribe(self, pattern: str, handler: Handler) -> None:
        self._handlers.setdefault(pattern, []).append(handler)
        self.client.subscribe(pattern, qos=1)

    def publish(self, topic: str, payload: dict, retain: bool = False) -> None:
        qos = 1 if topic.startswith("cps/alerts") or topic.endswith("/status") else 0
        self.client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=qos, retain=retain)

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
