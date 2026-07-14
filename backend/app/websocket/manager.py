"""WebSocket connection manager backed by Redis pub/sub (scale-ready).

Events are published to a single Redis channel; every worker's subscriber loop
fans them out to its local connections. So broadcasts work across multiple
workers/processes.

Event envelope:
    {"scope": "admin" | "exam" | "session", "type": "...",
     "exam_id": "...", "session_id": "...", "data": {...}}
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket

from app.core.redis import redis_client, redis_pubsub_client

logger = logging.getLogger("exam.ws")

CHANNEL = "ws:events"


class ConnectionManager:
    def __init__(self) -> None:
        self.admin: set[WebSocket] = set()
        self.by_exam: dict[str, set[WebSocket]] = {}
        self.by_session: dict[str, set[WebSocket]] = {}

    # --- connect / disconnect ---------------------------------------------
    async def connect_admin(self, ws: WebSocket) -> None:
        await ws.accept()
        self.admin.add(ws)

    def disconnect_admin(self, ws: WebSocket) -> None:
        self.admin.discard(ws)

    async def connect_exam(self, ws: WebSocket, exam_id: str, session_id: str) -> None:
        await ws.accept()
        self.by_exam.setdefault(exam_id, set()).add(ws)
        self.by_session.setdefault(session_id, set()).add(ws)

    def disconnect_exam(self, ws: WebSocket, exam_id: str, session_id: str) -> None:
        self.by_exam.get(exam_id, set()).discard(ws)
        self.by_session.get(session_id, set()).discard(ws)

    # --- publish / dispatch -----------------------------------------------
    async def publish(self, scope: str, type: str, *, exam_id=None, session_id=None, data=None) -> None:
        event = {
            "scope": scope,
            "type": type,
            "exam_id": str(exam_id) if exam_id else None,
            "session_id": str(session_id) if session_id else None,
            "data": data or {},
        }
        try:
            await redis_client.publish(CHANNEL, json.dumps(event, ensure_ascii=False, default=str))
        except Exception:  # noqa: BLE001 — WS is best-effort, never break the request
            logger.exception("WS publish failed")

    async def _dispatch(self, event: dict) -> None:
        scope = event.get("scope")
        if scope == "admin":
            targets = set(self.admin)
        elif scope == "exam":
            targets = set(self.by_exam.get(event.get("exam_id") or "", set()))
        elif scope == "session":
            targets = set(self.by_session.get(event.get("session_id") or "", set()))
        else:
            targets = set()
        for ws in targets:
            try:
                await ws.send_json(event)
            except Exception:  # noqa: BLE001 — drop dead sockets silently
                pass

    async def run_subscriber(self) -> None:
        # AD-75: Redis rớt 1 nhịp từng làm task này chết IM LẶNG → mọi WS event
        # (phát đề / cảnh báo giám thị) tắt tới khi restart — mà restart giữa buổi
        # là cấm. Bọc vòng ngoài: đứt thì re-subscribe sau 5s, không bao giờ bỏ cuộc.
        while True:
            # Client riêng không socket_timeout — listen() chờ lâu là bình thường.
            pubsub = redis_pubsub_client.pubsub()
            try:
                await pubsub.subscribe(CHANNEL)
                logger.info("WS subscriber listening on %s", CHANNEL)
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        await self._dispatch(json.loads(message["data"]))
                    except Exception:  # noqa: BLE001
                        logger.exception("WS dispatch failed")
            except asyncio.CancelledError:
                try:
                    await pubsub.unsubscribe(CHANNEL)
                    await pubsub.aclose()
                except Exception:  # noqa: BLE001
                    pass
                raise
            except Exception as exc:  # noqa: BLE001 — Redis blip: re-subscribe
                logger.warning("WS subscriber mất kết nối Redis (%s) — thử lại sau 5s", exc)
            try:
                await pubsub.aclose()
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(5)


manager = ConnectionManager()
