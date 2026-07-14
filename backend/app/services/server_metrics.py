"""Server-health metrics for the super_admin dashboard.

Runs inside the backend container, so CPU/RAM/disk/network reflect the Linux VM
that hosts all the containers (OrbStack on the Mac Mini) — which is exactly the
load surface that matters for the exam system. DB/Redis figures come straight
from those services. Each metric carries a simple ok/warn/danger status so the
UI can colour it and the operator can foresee trouble.
"""

from __future__ import annotations

import time

import psutil
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client

# Remember the previous network counters so we can derive a per-second rate
# without blocking the request to sample twice.
_net_prev: dict[str, float] = {}


def _status(value: float, warn: float, danger: float) -> str:
    if value >= danger:
        return "danger"
    if value >= warn:
        return "warn"
    return "ok"


def _system_metrics() -> dict:
    cpu_percent = psutil.cpu_percent(interval=None)
    cores = psutil.cpu_count(logical=True) or 1
    try:
        load1, load5, load15 = psutil.getloadavg()
    except (OSError, AttributeError):
        load1 = load5 = load15 = 0.0

    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    net = psutil.net_io_counters()
    now = time.monotonic()
    sent_rate = recv_rate = 0.0
    if _net_prev:
        dt = now - _net_prev["t"]
        if dt > 0:
            sent_rate = max(0.0, (net.bytes_sent - _net_prev["sent"]) / dt)
            recv_rate = max(0.0, (net.bytes_recv - _net_prev["recv"]) / dt)
    _net_prev.update(t=now, sent=net.bytes_sent, recv=net.bytes_recv)

    return {
        "cpu": {
            "percent": round(cpu_percent, 1),
            "cores": cores,
            "load_avg": [round(load1, 2), round(load5, 2), round(load15, 2)],
            # Load relative to core count is the real saturation signal.
            "status": _status(load1 / cores * 100, 70, 100),
        },
        "memory": {
            "total": vm.total,
            "used": vm.used,
            "percent": round(vm.percent, 1),
            "status": _status(vm.percent, 80, 92),
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "percent": round(disk.percent, 1),
            "status": _status(disk.percent, 80, 92),
        },
        "network": {
            "sent_per_sec": round(sent_rate),
            "recv_per_sec": round(recv_rate),
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
        },
        "uptime_seconds": int(time.time() - psutil.boot_time()),
    }


async def _db_metrics(db: AsyncSession) -> dict:
    try:
        used = int(await db.scalar(text("SELECT count(*) FROM pg_stat_activity")) or 0)
        max_conn = int(await db.scalar(text("SHOW max_connections")) or 0)
        size = int(await db.scalar(text("SELECT pg_database_size(current_database())")) or 0)
        pct = (used / max_conn * 100) if max_conn else 0
        return {
            "connections_used": used,
            "connections_max": max_conn,
            "connections_percent": round(pct, 1),
            "size_bytes": size,
            "status": _status(pct, 70, 90),
            "ok": True,
        }
    except Exception:  # noqa: BLE001 — dashboard must not 500 if a probe fails
        return {"ok": False}


async def _redis_metrics() -> dict:
    try:
        info = await redis_client.info()
        return {
            "used_memory": int(info.get("used_memory", 0)),
            "connected_clients": int(info.get("connected_clients", 0)),
            "ok": True,
        }
    except Exception:  # noqa: BLE001
        return {"ok": False}


async def collect(db: AsyncSession) -> dict:
    """Gather host + DB + Redis metrics for the dashboard."""
    return {
        "system": _system_metrics(),
        "database": await _db_metrics(db),
        "redis": await _redis_metrics(),
    }
