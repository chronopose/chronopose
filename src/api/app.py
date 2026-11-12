"""REST API, WebSocket и демо-панель (SCRUM-76, 77, 78, 79).

GET  /                         демо-панель (web/index.html)
GET  /api/health               живо ли приложение
GET  /api/cameras              камеры: источник, связь, кадры в секунду
GET  /api/cameras/{id}/stream  видео со скелетами (MJPEG, вставляется в <img>)
GET  /api/cameras/{id}/snapshot.jpg
GET  /api/people               люди в кадре: действие, вероятности, состояние движка
GET  /api/events?limit=50      журнал событий
GET  /api/events/{id}
GET  /api/sensors              телефоны-IMU и ESP32
WS   /ws/events                живые оповещения
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse

WEB = Path(__file__).resolve().parents[2] / "web"


class Hub:
    """Рассылка оповещений в открытые WebSocket. publish можно звать из любого потока."""

    def __init__(self) -> None:
        self.queues: Set[asyncio.Queue] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def publish(self, message: dict) -> None:
        if self.loop is None:
            return
        for q in list(self.queues):
            self.loop.call_soon_threadsafe(q.put_nowait, message)


class Context:
    """Всё, что нужно API: конвейер, журнал, приёмник IMU, камеры, состояния ESP32."""

    def __init__(self, pipeline, store=None, imu=None, bus=None) -> None:
        self.pipeline, self.store, self.imu, self.bus = pipeline, store, imu, bus
        self.cameras: Dict[str, object] = {}      # id → CameraRunner
        self.actuators: Dict[str, dict] = {}
        self.hub = Hub()
        self.started = time.time()
        pipeline.listeners.append(lambda alert: self.hub.publish({"type": "alert", "alert": alert.model_dump()}))
        if bus is not None:
            bus.subscribe("cps/actuators/+/status", self._actuator)
            bus.subscribe("cps/actuators/+/ack", self._actuator)

    def _actuator(self, topic: str, payload: dict) -> None:
        dev, kind = topic.split("/")[2], topic.split("/")[3]
        a = self.actuators.setdefault(dev, {"device_id": dev})
        value = payload.get("raw", payload)
        a["last_" + kind] = value
        a["last_seen"] = time.time()
        if kind == "status":
            a["online"] = value == "online"


def create_app(ctx: Context) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx.hub.loop = asyncio.get_running_loop()  # рассылка в WebSocket из потоков камеры
        yield

    app = FastAPI(title="chronopose", version="0.1.0", lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB / "index.html")

    @app.get("/api/health")
    def health():
        return {"ok": True, "uptime_s": round(time.time() - ctx.started, 1)}

    def camera(cam_id: str):
        cam = ctx.cameras.get(cam_id)
        if cam is None:
            raise HTTPException(404, f"нет камеры {cam_id}")
        return cam

    @app.get("/api/cameras")
    def cameras() -> List[dict]:
        return [c.info() for c in ctx.cameras.values()]

    @app.get("/api/cameras/{cam_id}/snapshot.jpg")
    def snapshot(cam_id: str):
        jpeg = camera(cam_id).jpeg
        if jpeg is None:
            raise HTTPException(503, "кадров ещё нет")
        return Response(jpeg, media_type="image/jpeg")

    @app.get("/api/cameras/{cam_id}/stream")
    async def stream(cam_id: str):
        cam = camera(cam_id)

        async def frames():
            last = None
            while True:
                jpeg = cam.jpeg
                if jpeg is not None and jpeg is not last:
                    last = jpeg
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                await asyncio.sleep(1 / 20)

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.get("/api/people")
    def people(camera_id: Optional[str] = None):
        return ctx.pipeline.people(camera_id)

    @app.get("/api/events")
    def events(limit: int = 50):
        if ctx.store is not None:
            return ctx.store.list(min(max(limit, 1), 500))
        return [a.model_dump() for a in reversed(ctx.pipeline.alerts[-limit:])]

    @app.get("/api/events/{event_id}")
    def event(event_id: str):
        ev = ctx.store.get(event_id) if ctx.store is not None else None
        if ev is None:
            raise HTTPException(404, "событие не найдено")
        return ev

    @app.get("/api/sensors")
    def sensors():
        return {"imu": list(ctx.imu.status().values()) if ctx.imu is not None else [],
                "actuators": list(ctx.actuators.values())}

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket):
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue()
        ctx.hub.loop = asyncio.get_running_loop()
        ctx.hub.queues.add(q)
        try:
            await ws.send_json({"type": "hello", "recent": [a.model_dump() for a in ctx.pipeline.alerts[-10:]]})
            while True:
                await ws.send_json(await q.get())
        except WebSocketDisconnect:
            pass
        finally:
            ctx.hub.queues.discard(q)

    return app
