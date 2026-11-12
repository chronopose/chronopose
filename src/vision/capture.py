"""Захват видео с телефона (SCRUM-30): IP Webcam отдаёт MJPEG по http://<ip>:8080/video.

Поток читается в отдельном потоке, наружу отдаётся только последний кадр — так обработка
не копит задержку, если модель медленнее камеры. При обрыве — переподключение.
Источник: URL, путь к файлу или номер веб-камеры ("0").
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Tuple

log = logging.getLogger("capture")


class VideoSource:
    def __init__(self, source: str, reconnect_delay: float = 2.0, loop_file: bool = True) -> None:
        self.source = int(source) if source.isdigit() else source
        self.reconnect_delay, self.loop_file = reconnect_delay, loop_file
        self._frame = None
        self._t = 0.0
        self._id = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.connected = False
        self.fps = 0.0
        self._thread = threading.Thread(target=self._run, name="capture", daemon=True)

    def start(self) -> VideoSource:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _open(self):
        import cv2

        cap = cv2.VideoCapture(self.source)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _run(self) -> None:
        import cv2

        is_file = isinstance(self.source, str) and not self.source.startswith(("http", "rtsp"))
        while not self._stop.is_set():
            cap = self._open()
            if not cap.isOpened():
                self.connected = False
                log.warning("нет видео от %s, повтор через %.0f с", self.source, self.reconnect_delay)
                time.sleep(self.reconnect_delay)
                continue
            self.connected = True
            log.info("видео подключено: %s", self.source)
            n, t_win = 0, time.time()
            delay = 1.0 / (cap.get(cv2.CAP_PROP_FPS) or 25.0) if is_file else 0.0
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    if is_file and self.loop_file:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    break
                with self._lock:
                    self._frame, self._t = frame, time.time()
                    self._id += 1
                n += 1
                if time.time() - t_win >= 2.0:
                    self.fps, n, t_win = n / (time.time() - t_win), 0, time.time()
                if delay:
                    time.sleep(delay)
            cap.release()
            self.connected = False
            log.warning("видео оборвалось, переподключение")
            time.sleep(self.reconnect_delay)

    def latest(self) -> Tuple[Optional[object], float, int]:
        """Последний кадр, время приёма и номер. Кадр None — пока нет ни одного."""
        with self._lock:
            return self._frame, self._t, self._id
