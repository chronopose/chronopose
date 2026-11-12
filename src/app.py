"""Запуск MVP одной командой.

Демо без железа (синтетическая камера и телефон, MQTT не нужен):
    python -m src.app --synthetic
Реальная система (телефон-камера, телефон-IMU через мост, Mosquitto):
    python -m src.app --camera http://192.168.1.21:8080/video --mqtt localhost --device imu_001
Панель: http://localhost:8000
"""
from __future__ import annotations

import argparse
import logging
import threading
import time
from typing import Optional

from src.api.app import Context, create_app
from src.bus import InMemoryBus, MqttBus
from src.contracts import Observation
from src.iot.receiver import ImuReceiver
from src.models.classifier import load_classifier
from src.pipeline import Pipeline
from src.storage import Store
from src.vision.draw import action_label, draw_overlay

log = logging.getLogger("app")


class CameraRunner:
    """Поток одной камеры: кадр → поза → конвейер → кадр со скелетами для панели."""

    def __init__(self, camera_id: str, pipeline: Pipeline, source: Optional[str] = None, synthetic: bool = False,
                 model: str = "yolo26n-pose.pt", fps: float = 15.0, scene_period: float = 20.0) -> None:
        self.id, self.pipeline, self.source, self.synthetic = camera_id, pipeline, source, synthetic
        self.model, self.target_fps, self.scene_period = model, fps, scene_period
        self.jpeg: Optional[bytes] = None
        self.fps = 0.0
        self.connected = False
        self.cycle_start = time.time()
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"camera-{camera_id}", daemon=True)

    def info(self) -> dict:
        return {"id": self.id, "source": "synthetic" if self.synthetic else self.source,
                "connected": self.connected, "fps": round(self.fps, 1),
                "people": len(self.pipeline.last_obs.get(self.id).people) if self.id in self.pipeline.last_obs else 0}

    def start(self) -> CameraRunner:
        self.thread.start()
        return self

    def _publish_frame(self, img, obs: Observation) -> None:
        import cv2

        labels, alarm = self.pipeline.labels(self.id)
        draw_overlay(img, obs, {k: action_label(v) for k, v in labels.items()}, alarm)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            self.jpeg = buf.tobytes()

    def _run(self) -> None:
        try:
            self._run_synthetic() if self.synthetic else self._run_camera()
        except Exception:  # поток камеры не должен молча умирать
            log.exception("камера %s остановилась", self.id)

    def _run_synthetic(self) -> None:
        from src.vision.synthetic import demo_scene

        self.connected = True
        frame_id, n, t_win = 0, 0, time.time()
        while not self._stop.is_set():
            self.cycle_start = time.time()
            scene = demo_scene(t0=self.cycle_start, fall_at=6.0)
            scene.camera_id = self.id
            while (t := time.time() - self.cycle_start) < self.scene_period and not self._stop.is_set():
                obs = scene.observation(frame_id, t)
                frame_id += 1
                self.pipeline.on_observation(obs)
                self._publish_frame(scene.render(obs), obs)
                n += 1
                if time.time() - t_win >= 2:
                    self.fps, n, t_win = n / (time.time() - t_win), 0, time.time()
                time.sleep(max(0.0, 1 / self.target_fps - (time.time() - self.cycle_start - t)))

    def _run_camera(self) -> None:
        from src.vision.capture import VideoSource
        from src.vision.pose import YoloPoseTracker

        estimator = YoloPoseTracker(self.model)
        src = VideoSource(self.source).start()
        last_id, n, t_win = -1, 0, time.time()
        while not self._stop.is_set():
            frame, t, fid = src.latest()
            self.connected = src.connected
            if frame is None or fid == last_id:
                time.sleep(0.005)
                continue
            last_id = fid
            h, w = frame.shape[:2]
            obs = Observation(camera_id=self.id, frame_id=fid, t=t, width=w, height=h, people=estimator(frame, t))
            self.pipeline.on_observation(obs)
            self._publish_frame(frame.copy(), obs)
            n += 1
            if time.time() - t_win >= 2:
                self.fps, n, t_win = n / (time.time() - t_win), 0, time.time()


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="chronopose MVP")
    p.add_argument("--camera", help="URL IP Webcam, путь к видео или номер веб-камеры")
    p.add_argument("--camera-id", default="cam_01")
    p.add_argument("--zone", default="A")
    p.add_argument("--synthetic", action="store_true", help="синтетическая камера и телефон, железо не нужно")
    p.add_argument("--mqtt", help="адрес Mosquitto; без него шина в памяти")
    p.add_argument("--device", default="imu_001", help="телефон-IMU, привязанный к камере")
    p.add_argument("--classifier", default="rules", choices=["rules", "forest"])
    p.add_argument("--model", default="yolo26n-pose.pt")
    p.add_argument("--db", default=None, help="sqlite:///data/chronopose.db или postgresql://…")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args(argv)
    if not a.synthetic and not a.camera:
        p.error("нужен --camera или --synthetic")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    bus = MqttBus(a.mqtt, client_id="chronopose-server") if a.mqtt else InMemoryBus()
    imu = ImuReceiver(bus)
    store = Store(a.db)
    pipe = Pipeline(bus=bus, store=store, imu=imu, devices={a.device: a.camera_id},
                    classifier=load_classifier(a.classifier), zones={a.camera_id: a.zone})
    ctx = Context(pipe, store, imu, bus)
    cam = CameraRunner(a.camera_id, pipe, a.camera, synthetic=a.synthetic, model=a.model).start()
    ctx.cameras[cam.id] = cam
    if a.synthetic and not a.mqtt:
        threading.Thread(target=_simulate_phone, args=(bus, a.device, cam), daemon=True).start()

    import uvicorn

    uvicorn.run(create_app(ctx), host=a.host, port=a.port, log_level="warning")


def _simulate_phone(bus, device: str, cam: CameraRunner) -> None:
    """Телефон-IMU в памяти, синхронно с циклами синтетической сцены: удар через 0,3 с после начала падения."""
    from src.iot.simulator import samples

    while True:
        start = cam.cycle_start
        for s in samples(device, t0=start, duration=cam.scene_period, fall_at=6.3):
            if cam.cycle_start != start:
                break
            time.sleep(max(0.0, s.t_server - time.time()))
            bus.publish(f"cps/imu/{device}/telemetry", s.model_dump())
        while cam.cycle_start == start:
            time.sleep(0.05)


if __name__ == "__main__":
    main()
