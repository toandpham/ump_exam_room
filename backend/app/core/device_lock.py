"""Single-active-device enforcement for candidates.

A candidate may only have one *live* device at a time. We track the currently
authorised token (its ``jti``) + originating IP in Redis. Every authenticated
candidate request re-affirms it: if the stored jti differs from the caller's,
that caller has been superseded by a newer login → 409. A heartbeat timestamp
lets the login flow tell a *live* other device (still polling) apart from a
stale leftover, so reconnecting on the same machine never nags.
"""

from __future__ import annotations

import json
import time

from app.config import settings
from app.core.redis import redis_client

# A device counts as "live" if it has polled within this many seconds. The exam
# client polls /state every 5s, so 25s tolerates a couple of missed beats.
LIVE_WINDOW_SECONDS = 25
_TTL = settings.jwt_expire_hours * 3600


def _key(candidate_id) -> str:
    return f"cand_active:{candidate_id}"


async def get_active(candidate_id) -> dict | None:
    raw = await redis_client.get(_key(candidate_id))
    return json.loads(raw) if raw else None


async def claim(candidate_id, jti: str, ip: str | None, dev: str | None = None) -> None:
    """Make ``jti`` the active device for this candidate (login / heartbeat).

    ``dev`` is the browser device-id (X-Device-Id) — the reliable per-machine
    signal. ``ip`` is kept for audit but is unreliable behind LAN NAT (every
    client appears as the reverse-proxy gateway IP)."""
    await redis_client.set(
        _key(candidate_id),
        json.dumps({"jti": jti, "ip": ip, "dev": dev, "ts": int(time.time())}),
        ex=_TTL,
    )


def is_live(active: dict | None) -> bool:
    if not active:
        return False
    return (time.time() - active.get("ts", 0)) < LIVE_WINDOW_SECONDS


async def revoke(candidate_id) -> None:
    """Proctor force-logout: park a sentinel jti so the candidate's CURRENT
    device is superseded (kicked → KickedScreen) on its next request, while a
    fresh login from any machine can still re-claim. ts=0 marks it not-live so
    the re-login doesn't trigger a takeover prompt."""
    await redis_client.set(
        _key(candidate_id),
        json.dumps({"jti": "__revoked__", "ip": None, "dev": None, "ts": 0}),
        ex=_TTL,
    )
