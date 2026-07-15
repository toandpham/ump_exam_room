"""Pytest fixtures: in-process httpx client against the FastAPI app + factories.

Tests talk to the real Postgres/Redis the container is wired to (no network —
ASGITransport calls the app directly). Everything created is registered and torn
down afterwards, and all test data uses a ``TST_`` / ``tst_`` marker so a failed
run never collides with real data.
"""

from __future__ import annotations

import json
import uuid
from datetime import date

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core import device_lock
from app.core.limiter import limiter
from app.core.redis import redis_client
from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.main import app
from app.models import Admin, Answer, Candidate, Exam, ExamSession, Room, Sitting
from app.models.enums import AdminRole, ExamStatus, SittingStatus
from app.services import session_service

# Tests fire many logins from the same client IP; the per-IP rate limit would
# trip and cause spurious 429s. Disable it for the suite.
limiter.enabled = False

# SEB is mandatory in production but the test suite (and dev without SEB) can't
# send a real Config Key header — disable enforcement here (AD-56).
from app.config import settings as _settings  # noqa: E402
_settings.seb_enforce = False

# Giấy phép server (AD-74): suite không có key thật (khoá bí mật nằm ngoài repo)
# — autouse coi như hợp lệ để 141 test cũ chạy nguyên. test_license.py giữ tham
# chiếu bản THẬT (real_current_state) để kiểm middleware/API đúng logic.
import pytest  # noqa: E402
from app.core.license import LicenseState as _LicenseState  # noqa: E402
from app.services import license_service as _license_service  # noqa: E402

real_current_state = _license_service.current_state


async def _license_always_valid():
    return _LicenseState("valid", None)


@pytest.fixture(autouse=True)
def _license_ok(monkeypatch):
    monkeypatch.setattr(_license_service, "current_state", _license_always_valid)


@pytest_asyncio.fixture(autouse=True)
async def _clear_active_exams_cache():
    """The active-exams / active-sitting Redis caches (AD-69) are global keys; clear
    them around every test so one test's exam state can't leak into another's
    /status, /kiosk or /state poll."""
    async def _clear():
        await redis_client.delete(session_service._ACTIVE_EXAMS_CACHE_KEY)
        sit_keys = await redis_client.keys("cache:active_sitting:*")
        if sit_keys:
            await redis_client.delete(*sit_keys)
    await _clear()
    yield
    await _clear()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def factory(db):
    """Create test entities and clean them all up at the end."""
    created: dict[str, list] = {"exams": [], "admins": [], "candidates": [], "sittings": []}

    class Factory:
        async def admin(self, role=AdminRole.PROCTOR.value, password="pw123456"):
            a = Admin(
                username=f"tst_{uuid.uuid4().hex[:10]}",
                password_hash=hash_password(password),
                full_name="Test Admin",
                role=role,
                is_active=True,
            )
            db.add(a)
            await db.commit()
            await db.refresh(a)
            created["admins"].append(a.id)
            token, _ = create_access_token(subject=str(a.id), username=a.username, role=a.role)
            return a, token

        async def owned_exam(self, owner_id, name=None):
            """A plain draft exam owned by ``owner_id`` — for ownership tests
            without tripping the global at-most-one-active invariant."""
            exam = Exam(
                name=name or f"TST_{uuid.uuid4().hex[:8]}",
                duration_minutes=30,
                status=ExamStatus.DRAFT.value,
                created_by=owner_id,
            )
            db.add(exam)
            await db.commit()
            await db.refresh(exam)
            created["exams"].append(exam.id)
            return exam

        async def active_exam(self, questions: list[dict], duration=45, owner_id=None, shuffle=False):
            """Create an active exam with one OPEN sitting (buổi) + push its payload
            to Redis (AD-47). ``questions`` is a list of {id?, text, correct,
            options:[id...]}. Returns ``(exam, sitting, payload)``.
            ``shuffle`` bật shuffle_questions + shuffle_options (mặc định False để
            test cũ không đổi; test trộn SP-2b dùng shuffle=True)."""
            payload_qs = []
            for i, q in enumerate(questions):
                qid = q.get("id") or str(uuid.uuid4())
                opts = q.get("options") or ["A", "B", "C", "D"]
                payload_qs.append({
                    "id": qid,
                    "code": q.get("code", ""),
                    "text": q["text"],
                    "images": [],
                    "options": [{"id": o, "text": f"Đáp án {o}", "images": []} for o in opts],
                    "correct_option": q["correct"],
                    "order_index": i,
                })
            exam = Exam(
                name=f"TST_{uuid.uuid4().hex[:8]}",
                description="test",
                duration_minutes=duration,
                exam_date=date.today(),
                status=ExamStatus.ACTIVE.value,
                created_by=owner_id,
            )
            db.add(exam)
            await db.flush()
            sitting = Sitting(
                exam_id=exam.id, name="Buổi thi 1", ordinal=1,
                duration_minutes=duration, status=SittingStatus.ACTIVE.value,
                shuffle_questions=shuffle, shuffle_options=shuffle,
                question_count=len(payload_qs),
                encrypted_payload=b"x",  # non-empty so distribute/start guards pass
                report_snapshot=[{"id": q["id"], "code": q.get("code", ""), "text": q["text"],
                                  "correct_option": q["correct_option"]} for q in payload_qs],
            )
            db.add(sitting)
            await db.commit()
            await db.refresh(exam)
            await db.refresh(sitting)
            created["exams"].append(exam.id)
            created["sittings"].append(sitting.id)
            payload = {"questions": payload_qs}
            await redis_client.set(session_service.payload_key(sitting.id),
                                   json.dumps(payload), ex=3600)
            return exam, sitting, payload

        async def empty_active_exam(self, owner_id, duration=45):
            """An ACTIVE exam with a DRAFT sitting that has no đề yet — for
            exercising the real QTI import path. Returns ``(exam, sitting)``."""
            exam = Exam(
                name=f"TST_{uuid.uuid4().hex[:8]}",
                duration_minutes=duration,
                exam_date=date.today(),
                status=ExamStatus.ACTIVE.value,
                created_by=owner_id,
            )
            db.add(exam)
            await db.flush()
            sitting = Sitting(
                exam_id=exam.id, name="Buổi thi 1", ordinal=1,
                duration_minutes=duration, status=SittingStatus.DRAFT.value,
            )
            db.add(sitting)
            await db.commit()
            await db.refresh(exam)
            await db.refresh(sitting)
            created["exams"].append(exam.id)
            created["sittings"].append(sitting.id)
            return exam, sitting

        async def room(self, exam_id, proctor_id=None, name="Phòng test"):
            r = Room(exam_id=exam_id, name=name, proctor_id=proctor_id)
            db.add(r)
            await db.commit()
            await db.refresh(r)
            return r

        async def candidate(self, exam_id, cccd=None, room_id=None, id_type="cccd"):
            c = Candidate(
                cccd=cccd or ("9" + uuid.uuid4().hex[:11].translate(
                    str.maketrans("abcdef", "012345"))),
                id_type=id_type,
                full_name="Nguyễn Văn Test",
                birth_date=date(2000, 1, 1),
                unit="Đơn vị test",
                category="Đối tượng 1",
                attempt_number=1,
                graduation_year=None,
                major=None,
                photo_path=None,
                exam_id=exam_id,
                room_id=room_id,
            )
            db.add(c)
            await db.commit()
            await db.refresh(c)
            created["candidates"].append(c.id)
            return c

    yield Factory()

    # Teardown — children first, respecting FKs.
    async with AsyncSessionLocal() as t:
        if created["candidates"]:
            sess_ids = list(await t.scalars(
                select(ExamSession.id).where(ExamSession.candidate_id.in_(created["candidates"]))
            ))
            if sess_ids:
                await t.execute(delete(Answer).where(Answer.session_id.in_(sess_ids)))
                await t.execute(delete(ExamSession).where(ExamSession.id.in_(sess_ids)))
        if created["exams"]:
            ex_sess = list(await t.scalars(
                select(ExamSession.id).where(ExamSession.exam_id.in_(created["exams"]))
            ))
            if ex_sess:
                await t.execute(delete(Answer).where(Answer.session_id.in_(ex_sess)))
                await t.execute(delete(ExamSession).where(ExamSession.id.in_(ex_sess)))
            await t.execute(delete(Candidate).where(Candidate.exam_id.in_(created["exams"])))
        if created["candidates"]:
            await t.execute(delete(Candidate).where(Candidate.id.in_(created["candidates"])))
        if created["exams"]:
            await t.execute(delete(Exam).where(Exam.id.in_(created["exams"])))
        if created["admins"]:
            await t.execute(delete(Admin).where(Admin.id.in_(created["admins"])))
        await t.commit()
    for cid in created["candidates"]:
        await redis_client.delete(device_lock._key(cid))
    for sid in created["sittings"]:
        await redis_client.delete(session_service.payload_key(sid))
        await redis_client.delete(session_service.report_cache_key(sid))


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


QENC_PASSWORD = "ACDE-FGHJ-KMNP-QRTU"   # mật khẩu đề dùng trong test


def qenc(zip_bytes: bytes, password: str = QENC_PASSWORD) -> bytes:
    """Bọc ZIP QTI thành .qenc như phần mềm Mã hoá đề thi (2 khoá: hệ thống + mật khẩu)."""
    from app.core import qti_crypt
    return qti_crypt.encrypt_qenc(zip_bytes, password)


async def fast_forward_start(sitting_id) -> None:
    """SP-2c: kéo started_at về quá khứ cho mọi phiên in_progress của buổi thi.

    Dùng trong test khi cần POST /answer ngay sau /start mà không phải chờ
    hết đếm ngược 20s thực. Không đổi end_time (thời gian làm bài giữ nguyên).
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import update as _update
    from app.models.enums import SessionStatus
    async with AsyncSessionLocal() as s:
        await s.execute(
            _update(ExamSession)
            .where(
                ExamSession.sitting_id == sitting_id,
                ExamSession.status == SessionStatus.IN_PROGRESS.value,
            )
            .values(started_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await s.commit()
