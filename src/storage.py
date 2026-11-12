"""Журнал событий: SQLite по умолчанию, PostgreSQL — если DATABASE_URL начинается с postgresql://.

SQL намеренно простой и общий для обеих баз. Таблица одна: события вместе с текстом оповещения.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import List, Optional

from src.contracts import Alert, Event

SCHEMA = """CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, person TEXT NOT NULL, camera_id TEXT NOT NULL, zone TEXT NOT NULL,
    t_start DOUBLE PRECISION NOT NULL, t_confirmed DOUBLE PRECISION NOT NULL, confidence DOUBLE PRECISION NOT NULL,
    imu_confirmed TEXT, text TEXT NOT NULL, payload TEXT NOT NULL)"""
COLS = ["id", "kind", "person", "camera_id", "zone", "t_start", "t_confirmed", "confidence", "imu_confirmed", "text"]


class Store:
    def __init__(self, url: Optional[str] = None) -> None:
        url = url or os.environ.get("DATABASE_URL", "sqlite:///data/chronopose.db")
        self._lock = threading.Lock()
        if url.startswith(("postgresql://", "postgres://")):
            import psycopg

            self.conn = psycopg.connect(url, autocommit=True)
            self.ph = "%s"
        else:
            path = url.replace("sqlite:///", "", 1) if url.startswith("sqlite:///") else url
            if path not in (":memory:", "") and os.path.dirname(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
            self.conn = sqlite3.connect(path or ":memory:", check_same_thread=False)
            self.ph = "?"
        with self._lock:
            self.conn.execute(SCHEMA)
            if self.ph == "?":
                self.conn.commit()

    def add(self, ev: Event, alert: Alert) -> None:
        imu = None if ev.imu_confirmed is None else str(ev.imu_confirmed).lower()
        row = [ev.id, ev.kind, ev.person, ev.camera_id, ev.zone, ev.t_start, ev.t_confirmed, ev.confidence,
               imu, alert.text, json.dumps({"event": ev.model_dump(), "alert": alert.model_dump()}, ensure_ascii=False)]
        sql = f"INSERT INTO events ({', '.join(COLS)}, payload) VALUES ({', '.join([self.ph] * (len(COLS) + 1))})"
        with self._lock:
            self.conn.execute(sql, row)
            if self.ph == "?":
                self.conn.commit()

    def _rows(self, sql: str, args=()) -> List[dict]:
        with self._lock:
            cur = self.conn.execute(sql, args)
            rows = cur.fetchall()
        out = []
        for r in rows:
            d = dict(zip(COLS, r))
            d["imu_confirmed"] = None if d["imu_confirmed"] is None else d["imu_confirmed"] == "true"
            out.append(d)
        return out

    def list(self, limit: int = 50) -> List[dict]:
        return self._rows(f"SELECT {', '.join(COLS)} FROM events ORDER BY t_confirmed DESC LIMIT {int(limit)}")

    def get(self, event_id: str) -> Optional[dict]:
        rows = self._rows(f"SELECT {', '.join(COLS)} FROM events WHERE id = {self.ph}", (event_id,))
        return rows[0] if rows else None
