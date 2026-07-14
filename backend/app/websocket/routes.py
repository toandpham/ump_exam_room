"""WebSocket endpoints: /ws/admin (monitor) and /ws/exam/{session_id} (candidate)."""

from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.database import AsyncSessionLocal
from app.models import Admin, ExamSession
from app.models.enums import EventType
from app.services import session_service
from app.websocket.manager import manager

router = APIRouter()


async def _auth_admin(token: str | None) -> Admin | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        return None
    if payload.get("typ") == "candidate":
        return None
    async with AsyncSessionLocal() as db:
        try:
            admin = await db.get(Admin, uuid.UUID(payload.get("sub", "")))
        except (ValueError, TypeError):
            return None
        return admin if admin and admin.is_active else None


async def _auth_session(token: str | None, session_id: uuid.UUID) -> ExamSession | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "candidate":
        return None
    async with AsyncSessionLocal() as db:
        session = await db.get(ExamSession, session_id)
        if session is None or str(session.candidate_id) != payload.get("sub"):
            return None
        return session


@router.websocket("/ws/admin")
async def admin_ws(websocket: WebSocket) -> None:
    admin = await _auth_admin(websocket.query_params.get("token"))
    if admin is None:
        await websocket.close(code=4401)
        return
    await manager.connect_admin(websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive pings; nothing to process
    except WebSocketDisconnect:
        manager.disconnect_admin(websocket)


@router.websocket("/ws/exam/{session_id}")
async def exam_ws(websocket: WebSocket, session_id: uuid.UUID) -> None:
    session = await _auth_session(websocket.query_params.get("token"), session_id)
    if session is None:
        await websocket.close(code=4401)
        return
    exam_id = str(session.exam_id)
    await manager.connect_exam(websocket, exam_id, str(session_id))
    try:
        while True:
            msg = await websocket.receive_json()
            await _handle_candidate_message(msg, session, exam_id)
    except WebSocketDisconnect:
        manager.disconnect_exam(websocket, exam_id, str(session_id))
    except Exception:  # noqa: BLE001 — malformed frames shouldn't crash the socket loop
        manager.disconnect_exam(websocket, exam_id, str(session_id))


async def _handle_candidate_message(msg: dict, session: ExamSession, exam_id: str) -> None:
    mtype = msg.get("type")
    if mtype == "tab_change":
        count = int(msg.get("count", 1))
        async with AsyncSessionLocal() as db:
            db.add(session_service.make_event(
                event_type=EventType.TAB_CHANGE.value,
                session_id=session.id,
                metadata={"count": count, "severe": count > 3},
            ))
            await db.commit()
        await manager.publish(
            "admin", "tab_change_warning", exam_id=exam_id, session_id=str(session.id),
            data={"count": count, "severe": count > 3},
        )
