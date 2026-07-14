"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.api.deps import require_roles
from app.models.enums import AdminRole

import asyncio

from app.api.admin import admins as admin_admins
from app.api.admin import auth as admin_auth
from app.api.admin import candidates as admin_candidates
from app.api.admin import exams as admin_exams
from app.api.admin import license as admin_license
from app.api.admin import monitor as admin_monitor
from app.api.admin import reports as admin_reports
from app.api.admin import rooms as admin_rooms
from app.api.admin import sittings as admin_sittings
from app.api.exam import answer as exam_answer
from app.api.exam import auth as exam_auth
from app.api.exam import session as exam_session
from app.bootstrap import ensure_room_proctors
from app.config import settings
from app.core.limiter import limiter, rate_limit_handler
from app.core.redis import redis_client
from app.database import AsyncSessionLocal
from app.services import license_service
from app.services.session_service import auto_submit_expired, reconcile_active_sittings
from app.websocket import routes as ws_routes
from app.websocket.manager import manager

# How often the per-candidate auto-submit sweep runs (AD-47).
_SWEEP_INTERVAL_SECONDS = 5

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger("exam")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting exam backend (env=%s)", settings.environment)
    try:
        await redis_client.ping()
        logger.info("Redis connection OK")
    except Exception as exc:  # noqa: BLE001 — log and continue; health surfaces issues
        logger.warning("Redis ping failed at startup: %s", exc)
    try:
        await ensure_room_proctors()
    except Exception as exc:  # noqa: BLE001 — never block startup on seeding
        logger.warning("ensure_room_proctors failed: %s", exc)
    try:
        # AD-81: đặt mốc cài đặt lần đầu → bắt đầu đếm dùng thử 90 ngày.
        async with AsyncSessionLocal() as _db:
            await license_service.ensure_installed(_db)
    except Exception as exc:  # noqa: BLE001 — never block startup on license row
        logger.warning("ensure_installed (license) failed: %s", exc)
    reloaded = await reconcile_active_sittings(redis_client)
    if reloaded:
        logger.info("Reloaded Redis payload for %d active sitting(s) after restart", reloaded)
    subscriber_task = asyncio.create_task(manager.run_subscriber())
    sweep_task = asyncio.create_task(_auto_submit_loop())
    yield
    for task in (subscriber_task, sweep_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await redis_client.aclose()
    logger.info("Shutting down exam backend")


async def _auto_submit_loop() -> None:
    """Background loop: auto-submit candidates whose own clock has run out (AD-47).
    Each candidate has an independent timer; this is the only thing that ends a
    candidate's exam by time. Errors are logged and the loop keeps running."""
    while True:
        try:
            await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)
            # Multi-worker safe (AD-69): with several uvicorn workers, each runs this
            # loop — only the one that grabs the Redis lock does the sweep this tick.
            # TTL PHẢI dài hơn lần quét xấu nhất (500 phiên hết giờ cùng lúc — AD-75):
            # TTL ngắn từng cho phép worker thứ 2 chiếm lock giữa chừng và chấm chồng.
            # Xong việc thì DEL để tick kế không phải đợi hết TTL.
            if not await redis_client.set("lock:auto_submit_sweep", "1", nx=True, ex=60):
                continue
            try:
                n = await auto_submit_expired(redis_client)
                if n:
                    logger.info("Auto-submitted %d expired session(s)", n)
            finally:
                try:
                    await redis_client.delete("lock:auto_submit_sweep")
                except Exception:  # noqa: BLE001 — mất DEL thì TTL 60s tự nhả
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — never let the sweep die
            logger.error("auto_submit sweep error: %s", exc)


app = FastAPI(
    title="Exam System API",
    version="0.1.0",
    lifespan=lifespan,
    # Hide the API surface (Swagger UI + schema) in production — candidates are
    # on the same LAN and have no business browsing endpoints. Kept in dev.
    docs_url=None if settings.is_production else "/api/docs",
    openapi_url=None if settings.is_production else "/api/openapi.json",
)

# Rate limiting (slowapi)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Giấy phép server (AD-74) ────────────────────────────────────────────────
# Không có key hợp lệ → mọi /api/* trả 403 license_*, TRỪ danh sách dưới đây
# (đủ để super_admin đăng nhập + nhập key mới, và healthcheck sống).
_LICENSE_SKIP = (
    "/api/health",
    "/api/admin/auth/login",
    "/api/admin/auth/logout",
    "/api/admin/auth/me",
    "/api/admin/license",
)
_LICENSE_CODES = {
    "missing": ("license_missing", "Server chưa có giấy phép — nhập license key"),
    "expired": ("license_expired", "Giấy phép đã hết hạn — liên hệ nhà cung cấp để lấy key mới"),
    "clock_tampered": ("license_clock", "Đồng hồ hệ thống bất thường — liên hệ nhà cung cấp"),
}


@app.middleware("http")
async def license_gate(request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not path.startswith(_LICENSE_SKIP):
        state = await license_service.current_state()
        if not state.ok:
            from fastapi.responses import JSONResponse

            code, detail = _LICENSE_CODES[state.status]
            return JSONResponse(status_code=403, content={"detail": detail, "code": code})
    return await call_next(request)

# Routers. candidates/reports are proctor-only (chủ tịch — super_admin doesn't
# intervene, AD-25). exams/sittings/monitor are guarded per-endpoint inside the
# module (monitor mixes chủ tịch control with giám thị pause/resume, AD-47).
_proctor_only = [Depends(require_roles(AdminRole.PROCTOR.value))]
app.include_router(admin_auth.router, prefix="/api/admin/auth", tags=["admin-auth"])
app.include_router(admin_license.router, prefix="/api/admin/license", tags=["admin-license"])
app.include_router(admin_admins.router, prefix="/api/admin/admins", tags=["admin-admins"])
app.include_router(admin_exams.router, prefix="/api/admin/exams", tags=["admin-exams"])
app.include_router(admin_sittings.router, prefix="/api/admin", tags=["admin-sittings"])
app.include_router(admin_rooms.router, prefix="/api/admin", tags=["admin-rooms"])
app.include_router(admin_candidates.router, prefix="/api/admin/candidates", tags=["admin-candidates"], dependencies=_proctor_only)
app.include_router(admin_monitor.router, prefix="/api/admin", tags=["admin-monitor"])
app.include_router(admin_reports.router, prefix="/api/admin", tags=["admin-reports"])
app.include_router(exam_auth.router, prefix="/api/exam/auth", tags=["exam-auth"])
app.include_router(exam_session.router, prefix="/api/exam", tags=["exam-session"])
app.include_router(exam_answer.router, prefix="/api/exam", tags=["exam-answer"])
app.include_router(ws_routes.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness probe used by the Docker healthcheck and Caddy."""
    return {"status": "ok", "service": "exam-backend"}


@app.get("/api/health", tags=["health"])
async def api_health() -> dict[str, str]:
    """Same probe under the /api prefix routed by Caddy."""
    return {"status": "ok", "service": "exam-backend"}
