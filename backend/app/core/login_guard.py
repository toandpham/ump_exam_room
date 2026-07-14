"""Escalating per-IP lockout for admin login.

slowapi gives a flat window; here the lockout GROWS each time an IP keeps
failing after the threshold: 1st lockout = STEP seconds, 2nd = 2×STEP, 3rd =
3×STEP … capped at CAP. Backed by Redis so it survives restarts / multiple
workers. A successful login clears everything; the escalation level decays after
an hour of good behaviour.
"""

from __future__ import annotations

import time

from app.core.limiter import limiter
from app.core.redis import redis_client

THRESHOLD = 10      # wrong tries allowed before a lockout kicks in
STEP = 60           # base lockout seconds (level 1 = 60s, level 2 = 120s …)
CAP = 600           # max lockout (10 min)
FAIL_TTL = 600      # the wrong-try counter resets after this idle window
LEVEL_TTL = 3600    # escalation level decays after an hour without new lockouts


def _k(part: str, ip: str) -> str:
    return f"loginlock:{part}:{ip}"


async def seconds_locked(ip: str) -> int:
    """Seconds remaining on the current lockout (0 if not locked)."""
    if not limiter.enabled:   # tests disable throttling (conftest)
        return 0
    raw = await redis_client.get(_k("until", ip))
    if not raw:
        return 0
    return max(0, int(float(raw) - time.time()))


async def register_failure(ip: str) -> int:
    """Record a wrong attempt. If it trips the threshold, start (or escalate) a
    lockout and return its length in seconds; otherwise return 0."""
    if not limiter.enabled:   # tests disable throttling (conftest)
        return 0
    fails = await redis_client.incr(_k("fails", ip))
    if fails == 1:
        await redis_client.expire(_k("fails", ip), FAIL_TTL)
    if fails < THRESHOLD:
        return 0
    level = await redis_client.incr(_k("level", ip))
    await redis_client.expire(_k("level", ip), LEVEL_TTL)
    duration = min(STEP * level, CAP)
    await redis_client.set(_k("until", ip), time.time() + duration, ex=duration + 1)
    await redis_client.delete(_k("fails", ip))   # reset counter for the next batch
    return duration


async def clear(ip: str) -> None:
    """Wipe the lockout state for an IP (call on a successful login)."""
    await redis_client.delete(_k("fails", ip), _k("until", ip), _k("level", ip))
