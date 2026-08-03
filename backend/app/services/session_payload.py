"""Khoá Redis + truy cập payload đề của buổi thi (tách từ session_service, refactor
đợt 3). Gồm: các hàm dựng khoá Redis, nạp/giải mã payload (single-flight + TTL
trượt), cache danh sách kỳ thi/buổi đang mở.

Mọi tên ở đây được re-export qua ``app.services.session_service`` — call site cũ
không phải đổi import."""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Exam, Sitting
from app.models.enums import ExamStatus, SittingStatus
from app.services import exam_assets, exam_package

logger = logging.getLogger("exam.session")


def payload_key(sitting_id) -> str:
    """Redis key holding a sitting's decrypted đề payload (AD-47)."""
    return f"sitting:{sitting_id}:payload"


def kiosk_quit_key(exam_id) -> str:
    """Redis flag asking all kiosk machines of this exam to quit (AD-66).
    Short TTL so a machine booted after the window is not closed unexpectedly."""
    return f"kiosk_quit:{exam_id}"


def kiosk_quit_device_key(device_id: str) -> str:
    """Cờ Redis yêu cầu ĐÚNG MỘT máy thoát (AD-128) — dùng cho lệnh thoát theo
    từng thí sinh / theo phòng của giám thị. Khoá theo ``device_id`` mà kiosk khai
    lúc hỏi lệnh (IP vô dụng vì mọi máy ra cùng gateway Docker — AD-35).
    Hạn ngắn như cờ cả kỳ thi để máy bật lại sau đó không bị đóng oan."""
    return f"kiosk_quit_dev:{device_id}"


def kiosk_wipe_key(exam_id) -> str:
    """Redis flag yêu cầu mọi máy kiosk của kỳ thi này XOÁ đề + đáp án local
    (HTTP cache + storage) rồi về đăng nhập (SP-4). Set khi đóng buổi, xoá khi
    mở buổi. Khác `kiosk_quit_key` (thoát hẳn máy)."""
    return f"kiosk_wipe:{exam_id}"


def report_cache_key(sitting_id) -> str:
    """Redis key for a sitting's lazily-built answer-key cache (reports)."""
    return f"sitting:{sitting_id}:report"


def preload_key(session_id) -> str:
    """Cờ 'máy đã tải xong toàn bộ ảnh đề' của một phiên (AD-110). Máy thí sinh
    báo về khi tải đủ lúc CHỜ bắt đầu; bảng giám sát đếm để chủ tịch chỉ bấm
    'Bắt đầu thi' khi mọi máy đã sẵn đề (hết cảnh khúc đầu buổi thi ì vì tải nền)."""
    return f"preload_done:{session_id}"



def storage_key() -> str:
    """Server-side key used to encrypt the QTI payload at rest. Derived from
    JWT_SECRET so it's unique per deployment and never exposed to admins."""
    return "qti-storage:" + settings.jwt_secret


async def get_sitting_payload(redis, sitting_id) -> dict | None:
    """Load and parse a sitting's decrypted đề payload from Redis (None if absent)."""
    raw = await redis.get(payload_key(sitting_id))
    if raw is None:
        return None
    return json.loads(raw)


def _payload_ttl(sitting: Sitting) -> int:
    return sitting.duration_minutes * 60 + 1800


def _rebuild_payload_sync(sitting_id, blob: bytes) -> dict:
    """Giải mã + materialize ảnh — CPU-bound, PHẢI chạy trong thread (to_thread)."""
    file_obj = exam_package.parse_exam_file(blob)
    payload = exam_package.decrypt_exam_file(file_obj, storage_key())
    return exam_assets.materialize_payload_images(sitting_id, payload)


async def ensure_sitting_payload(db: AsyncSession, redis, sitting: Sitting) -> dict | None:
    """Return the sitting's live đề payload, self-healing if Redis lost it.

    Redis payload có TTL (đặt lúc mở buổi = duration·60+1800). Nếu buổi mở sớm rồi
    lâu sau mới "Bắt đầu thi" (hoặc cộng giờ / thí sinh vào trễ), đồng hồ thi có thể
    chạy QUÁ mốc TTL → payload biến mất giữa buổi. Khi Redis trống ta giải mã lại từ
    ``encrypted_payload`` (bền tại DB tới khi đóng buổi), materialize ảnh tĩnh, nạp
    lại Redis. Trả None nếu đề đã bị purge (đóng buổi).

    Chống thundering-herd (AD-75): N request /questions cùng lúc phát hiện Redis
    trống sẽ KHÔNG cùng giải mã (PBKDF2 600k + blob trăm MB, từng nghẽn event loop
    13-07) — chỉ 1 request giữ khoá Redis dựng lại (trong thread), số còn lại chờ
    rồi đọc kết quả. Đọc trúng payload cũng GIA HẠN TTL trượt để không bao giờ hết
    hạn giữa lúc còn người thi."""
    payload = await get_sitting_payload(redis, sitting.id)
    if payload is not None:
        try:
            await redis.expire(payload_key(sitting.id), _payload_ttl(sitting))
        except Exception:  # noqa: BLE001 — gia hạn hụt không được chặn request
            pass
        return payload

    lock_key = f"lock:payload_rebuild:{sitting.id}"
    got_lock = await redis.set(lock_key, "1", nx=True, ex=120)
    if not got_lock:
        # Người khác đang dựng — chờ tối đa ~20s rồi đọc lại.
        for _ in range(40):
            await asyncio.sleep(0.5)
            payload = await get_sitting_payload(redis, sitting.id)
            if payload is not None:
                return payload
            if not await redis.exists(lock_key):
                break  # người dựng xong (hoặc lỗi) — thử tự dựng bên dưới
        got_lock = await redis.set(lock_key, "1", nx=True, ex=120)
        if not got_lock:
            return await get_sitting_payload(redis, sitting.id)

    try:
        # Double-check sau khi có khoá: có thể vừa được dựng xong.
        payload = await get_sitting_payload(redis, sitting.id)
        if payload is not None:
            return payload
        blob = await sitting_payload_blob(db, sitting.id)
        if not blob:
            return None
        try:
            payload = await asyncio.to_thread(_rebuild_payload_sync, sitting.id, blob)
        except Exception as exc:  # noqa: BLE001 — bad/foreign blob, đừng làm sập request
            logger.error("ensure_sitting_payload: không giải mã được đề buổi %s: %s",
                         sitting.id, exc)
            return None
        await redis.set(payload_key(sitting.id),
                        json.dumps(payload, ensure_ascii=False), ex=_payload_ttl(sitting))
        logger.info("Tự nạp lại Redis payload cho buổi %s (TTL hết giữa buổi)", sitting.id)
        return payload
    finally:
        try:
            await redis.delete(lock_key)
        except Exception:  # noqa: BLE001
            pass


_ACTIVE_EXAMS_CACHE_KEY = "cache:active_exams"
_ACTIVE_EXAMS_TTL = 5   # giây — đổi trạng thái kỳ thi phản ánh chậm tối đa ngần này


async def cached_active_exams(db: AsyncSession, redis) -> list[dict]:
    """Danh sách kỳ thi đang ACTIVE, cache Redis ~5s (AD-69). Endpoint poll cực
    nhiều (/kiosk/command từ MỌI máy + /status từ máy chưa đăng nhập, mỗi 5s) trước
    đây đều chạy `SELECT exams WHERE active` xuống DB mỗi lần → query áp đảo gây treo
    pool khi đông. Kết quả giống nhau cho mọi máy & đổi rất hiếm nên cache an toàn.
    Lỗi Redis → tự lùi về truy vấn DB (không bao giờ chặn). Trả [{id,name,
    allow_registration}]."""
    try:
        raw = await redis.get(_ACTIVE_EXAMS_CACHE_KEY)
        if raw is not None:
            return json.loads(raw)
    except Exception:  # noqa: BLE001 — Redis trục trặc thì đọc DB
        pass
    rows = list(await db.scalars(
        select(Exam).where(Exam.status == ExamStatus.ACTIVE.value).order_by(Exam.name)
    ))
    data = [
        {"id": str(e.id), "name": e.name, "allow_registration": bool(e.allow_registration)}
        for e in rows
    ]
    try:
        await redis.set(_ACTIVE_EXAMS_CACHE_KEY, json.dumps(data, ensure_ascii=False),
                        ex=_ACTIVE_EXAMS_TTL)
    except Exception:  # noqa: BLE001
        pass
    return data


async def cached_active_sitting_id(db: AsyncSession, redis, exam_id) -> str | None:
    """ID buổi đang ACTIVE của kỳ thi, cache Redis ~3s (AD-69). Dùng cho ĐƯỜNG ĐỌC
    nóng `/state` — endpoint mọi thí sinh poll /5s, trước đây chạy `SELECT
    exam_sittings WHERE exam_id+active` xuống DB MỖI lần → query áp đảo ngốn CPU
    Postgres khi đông. Chỉ trả id (đủ cho /state tìm phiên). Các đường điều khiển
    (login/answer/đóng buổi) vẫn dùng get_active_sitting (DB, không cache) cho an
    toàn. Stale tối đa ~3s khi mở/đóng buổi — chấp nhận được. Lỗi Redis → đọc DB."""
    key = f"cache:active_sitting:{exam_id}"
    try:
        raw = await redis.get(key)
        if raw is not None:
            return raw or None   # "" = không có buổi active
    except Exception:  # noqa: BLE001
        pass
    sitting = await get_active_sitting(db, exam_id)
    sid = str(sitting.id) if sitting else ""
    try:
        await redis.set(key, sid, ex=3)
    except Exception:  # noqa: BLE001
        pass
    return sid or None


async def sitting_has_payload(db: AsyncSession, sitting_id) -> bool:
    """Đề đã nạp chưa — check IS NOT NULL, KHÔNG kéo blob (cột deferred)."""
    return bool(await db.scalar(
        select(Sitting.encrypted_payload.isnot(None)).where(Sitting.id == sitting_id)
    ))


async def sitting_payload_blob(db: AsyncSession, sitting_id) -> bytes | None:
    """Đọc blob đề mã hoá bằng SELECT tường minh (cột deferred trên model)."""
    return await db.scalar(
        select(Sitting.encrypted_payload).where(Sitting.id == sitting_id)
    )


async def get_active_sitting(db: AsyncSession, exam_id) -> Sitting | None:
    """The one ``active`` sitting (buổi đang mở) of an exam, if any (AD-47)."""
    return await db.scalar(
        select(Sitting).where(
            Sitting.exam_id == exam_id,
            Sitting.status == SittingStatus.ACTIVE.value,
        ).limit(1)
    )

