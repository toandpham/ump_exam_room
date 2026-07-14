#!/usr/bin/env python3
"""SP-5b — WebSocket load test for the exam backend.

Phases
------
1. Login  : N candidates via HTTP POST /api/exam/auth/login (concurrent, unique
            X-Device-Id per candidate); GET /api/exam/state for session_id.
2. Hold   : open N WebSocket connections to /ws/exam/{session_id}?token=<jwt>;
            each socket sends tab_change every 15 s; drain incoming messages.
3. Fanout : while sockets are held, POST /sittings/{id}/extend (1 min) to
            publish an exam-scoped Redis event; measure receipt % + latency.
4. Reconnect storm : close all N sockets at once, immediately reopen all N.
5. Summary: print metrics, close cleanly.

Usage (inside the compose network)
------------------------------------
    pip install websockets aiohttp
    python /mnt/ws_load.py                     # defaults N=1000 hold=45s
    python /mnt/ws_load.py --host backend:8000 --n 500 --hold 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

# ─── CLI ─────────────────────────────────────────────────────────────────────
def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WS load test — SP-5b")
    p.add_argument("--host",  default="backend:8000", help="backend host:port")
    p.add_argument("--n",     type=int, default=1000, help="candidate count")
    p.add_argument("--hold",  type=int, default=45,   help="hold duration in seconds")
    p.add_argument("--proctor-user", default="proctor1")
    p.add_argument("--proctor-pass", default="proctor123")
    p.add_argument("--login-concurrency", type=int, default=100,
                   help="max concurrent HTTP login requests")
    return p.parse_args()


# ─── Data ────────────────────────────────────────────────────────────────────
@dataclass
class Cand:
    idx: int
    cccd: str
    dev_id: str
    token: str = ""
    session_id: str = ""
    login_ok: bool = False


@dataclass
class Metrics:
    n: int = 0
    login_ok: int = 0
    login_fail: int = 0
    login_wall_s: float = 0.0

    ws_connect_ok: int = 0
    ws_connect_fail: int = 0
    time_to_all_connected_s: float = 0.0
    messages_received: int = 0

    fanout_done: bool = False
    fanout_triggered_ok: bool = False
    fanout_receipt_count: int = 0
    fanout_receipt_pct: float = 0.0
    fanout_latencies_ms: list[float] = field(default_factory=list)

    reconnect_ok: int = 0
    reconnect_fail: int = 0
    reconnect_wall_s: float = 0.0


# ─── Phase 1 helpers ──────────────────────────────────────────────────────────
async def _login_one(
    session: aiohttp.ClientSession,
    cand: Cand,
    sem: asyncio.Semaphore,
    base: str,
) -> None:
    """Login + state for one candidate; sets cand.login_ok on success."""
    async with sem:
        try:
            hdrs = {"X-Device-Id": cand.dev_id}
            async with session.post(
                f"{base}/api/exam/auth/login",
                json={"cccd": cand.cccd, "force": True},
                headers=hdrs,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                if r.status != 200:
                    return
                data = await r.json()
            token = data.get("token")
            if not token:
                return
            # Get session_id from /state
            async with session.get(
                f"{base}/api/exam/state",
                headers={**hdrs, "Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                if r.status != 200:
                    return
                st = await r.json()
            sid = st.get("session_id")
            if not sid:
                return
            cand.token = token
            cand.session_id = sid
            cand.login_ok = True
        except Exception:
            pass  # login_ok stays False


async def phase_login(cands: list[Cand], base: str, concurrency: int) -> float:
    """Log in all candidates; returns wall-time seconds."""
    sem = asyncio.Semaphore(concurrency)
    t0 = time.monotonic()
    async with aiohttp.ClientSession() as http:
        await asyncio.gather(*[_login_one(http, c, sem, base) for c in cands])
    return time.monotonic() - t0


# ─── Admin token + sitting ID ─────────────────────────────────────────────────
async def get_admin_token(base: str, username: str, password: str) -> Optional[str]:
    async with aiohttp.ClientSession() as http:
        try:
            async with http.post(
                f"{base}/api/admin/auth/login",
                json={"username": username, "password": password},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    return (await r.json()).get("access_token")
        except Exception:
            pass
    return None


async def get_load_sitting_id(base: str, token: str) -> Optional[str]:
    """Return the active sitting_id of the LOAD TEST exam."""
    async with aiohttp.ClientSession() as http:
        hdrs = {"Authorization": f"Bearer {token}"}
        try:
            async with http.get(
                f"{base}/api/admin/exams",
                headers=hdrs,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status != 200:
                    return None
                exams = await r.json()
            exam_id = None
            for ex in (exams if isinstance(exams, list) else []):
                if "LOAD TEST" in ex.get("name", ""):
                    exam_id = ex["id"]
                    break
            if not exam_id:
                return None
            async with http.get(
                f"{base}/api/admin/exams/{exam_id}/sittings",
                headers=hdrs,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status != 200:
                    return None
                sittings = await r.json()
            for s in (sittings if isinstance(sittings, list) else []):
                if s.get("status") == "active":
                    return s["id"]
        except Exception:
            pass
    return None


# ─── Phase 2/4 helpers ───────────────────────────────────────────────────────
async def _ws_worker(
    cand: Cand,
    ws_base: str,
    # shared state
    n_connected: list[int],
    connect_results: list[bool],
    msg_count: list[int],
    # fanout
    fanout_t0: list[float],
    fanout_latencies: list[float],
    # control
    stop_event: asyncio.Event,
    connect_event: asyncio.Event,  # set when n_connected reaches threshold
    expected: int,
) -> None:
    """Open WS, hold until stop_event, record messages + fanout latency."""
    uri = f"{ws_base}/ws/exam/{cand.session_id}?token={cand.token}"
    try:
        async with websockets.connect(
            uri,
            ping_interval=None,
            ping_timeout=None,
            open_timeout=15,
            max_size=2**20,
            additional_headers={"X-Device-Id": cand.dev_id},
        ) as ws:
            n_connected[0] += 1
            connect_results.append(True)
            if n_connected[0] >= expected and not connect_event.is_set():
                connect_event.set()

            last_ping = time.monotonic()
            fanout_marked = False

            while not stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    msg_count[0] += 1
                    # Record fanout latency for first message after fanout_t0 is set
                    t0 = fanout_t0[0]
                    if t0 > 0 and not fanout_marked:
                        elapsed = time.monotonic() - t0
                        if elapsed >= 0:
                            fanout_latencies.append(elapsed * 1000)  # ms
                        fanout_marked = True
                except asyncio.TimeoutError:
                    pass
                except (ConnectionClosed, WebSocketException):
                    break

                # Send tab_change every 15s
                now = time.monotonic()
                if now - last_ping >= 15.0:
                    try:
                        await ws.send(json.dumps({"type": "tab_change", "count": 1}))
                    except Exception:
                        break
                    last_ping = now

            # Graceful close (stop_event fired or loop exited on error)
            try:
                await ws.close()
            except Exception:
                pass
    except Exception:
        connect_results.append(False)


async def phase_connect_and_hold(
    cands: list[Cand],
    ws_base: str,
    hold_seconds: float,
    metrics: Metrics,
    admin_token: Optional[str],
    sitting_id: Optional[str],
    http_base: str,
) -> None:
    """Phase 2: connect all sockets, fanout, hold, record."""
    n_connected: list[int] = [0]
    connect_results: list[bool] = []
    msg_count: list[int] = [0]
    fanout_t0: list[float] = [0.0]
    fanout_latencies: list[float] = []
    stop_event = asyncio.Event()
    connect_event = asyncio.Event()
    expected = len(cands)

    print(f"  Launching {expected} WS tasks …")
    t0_connect = time.monotonic()

    tasks = [
        asyncio.create_task(_ws_worker(
            c, ws_base,
            n_connected, connect_results, msg_count,
            fanout_t0, fanout_latencies,
            stop_event, connect_event, expected,
        ))
        for c in cands
    ]

    # Wait up to 60s for all to connect
    try:
        await asyncio.wait_for(connect_event.wait(), timeout=60.0)
        dt_connect = time.monotonic() - t0_connect
        metrics.time_to_all_connected_s = dt_connect
        print(f"  All {n_connected[0]} sockets connected in {dt_connect:.2f}s")
    except asyncio.TimeoutError:
        dt_connect = time.monotonic() - t0_connect
        metrics.time_to_all_connected_s = dt_connect
        print(f"  Timeout after {dt_connect:.1f}s — {n_connected[0]}/{expected} connected")

    connected_count = n_connected[0]

    # Phase 3 — fanout
    if sitting_id and admin_token and connected_count > 0:
        print(f"\n[Phase 3] Triggering fanout (sitting {sitting_id[:8]}…) …")
        await asyncio.sleep(1.0)  # let all sockets settle
        fanout_t0[0] = time.monotonic()  # arm latency timer
        async with aiohttp.ClientSession() as http:
            try:
                async with http.post(
                    f"{http_base}/api/admin/sittings/{sitting_id}/extend",
                    json={"minutes": 1},
                    headers={"Authorization": f"Bearer {admin_token}"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as r:
                    metrics.fanout_triggered_ok = r.status == 200
                    if not metrics.fanout_triggered_ok:
                        txt = await r.text()
                        print(f"  Fanout HTTP {r.status}: {txt[:200]}")
            except Exception as e:
                print(f"  Fanout error: {e}")
        metrics.fanout_done = True
        # Wait up to 10s for messages to arrive
        await asyncio.sleep(10.0)
        n_recv = len(fanout_latencies)
        metrics.fanout_receipt_count = n_recv
        metrics.fanout_receipt_pct = n_recv / connected_count * 100 if connected_count > 0 else 0
        metrics.fanout_latencies_ms = fanout_latencies[:]
        lats_s = sorted(fanout_latencies)
        med = lats_s[len(lats_s)//2] if lats_s else None
        p95 = lats_s[int(len(lats_s)*0.95)] if lats_s else None
        print(f"  Fanout trigger OK: {metrics.fanout_triggered_ok}")
        print(f"  Receipt: {n_recv}/{connected_count} ({metrics.fanout_receipt_pct:.1f}%)")
        if med is not None:
            print(f"  Latency: median={med:.1f}ms  P95={p95:.1f}ms")
    else:
        reason = "no sitting_id" if not sitting_id else ("no admin_token" if not admin_token else "0 sockets connected")
        print(f"\n[Phase 3] Skipping fanout ({reason})")

    # Remaining hold time
    elapsed_so_far = time.monotonic() - t0_connect
    remaining = hold_seconds - elapsed_so_far
    if remaining > 0:
        print(f"\n  Holding {remaining:.0f}s more …")
        await asyncio.sleep(remaining)

    metrics.messages_received = msg_count[0]
    print(f"  Total messages received during hold: {msg_count[0]}")

    # Stop all workers
    stop_event.set()
    await asyncio.gather(*tasks, return_exceptions=True)

    metrics.ws_connect_ok = sum(1 for r in connect_results if r)
    metrics.ws_connect_fail = len(cands) - metrics.ws_connect_ok


async def phase_reconnect_storm(
    cands: list[Cand],
    ws_base: str,
    metrics: Metrics,
) -> None:
    """Phase 4: immediately open all N sockets again after closing them."""
    expected = len(cands)
    n_connected: list[int] = [0]
    connect_results: list[bool] = []
    msg_count: list[int] = [0]
    fanout_t0: list[float] = [0.0]   # not used in storm
    fanout_latencies: list[float] = []
    stop_event = asyncio.Event()
    connect_event = asyncio.Event()

    t0 = time.monotonic()
    tasks = [
        asyncio.create_task(_ws_worker(
            c, ws_base,
            n_connected, connect_results, msg_count,
            fanout_t0, fanout_latencies,
            stop_event, connect_event, expected,
        ))
        for c in cands
    ]
    try:
        await asyncio.wait_for(connect_event.wait(), timeout=60.0)
        dt = time.monotonic() - t0
        metrics.reconnect_wall_s = dt
        print(f"  Storm: {n_connected[0]}/{expected} connected in {dt:.2f}s")
    except asyncio.TimeoutError:
        dt = time.monotonic() - t0
        metrics.reconnect_wall_s = dt
        print(f"  Storm timeout after {dt:.1f}s — {n_connected[0]}/{expected}")

    stop_event.set()
    await asyncio.gather(*tasks, return_exceptions=True)
    metrics.reconnect_ok = sum(1 for r in connect_results if r)
    metrics.reconnect_fail = len(cands) - metrics.reconnect_ok


# ─── Main ─────────────────────────────────────────────────────────────────────
async def main() -> None:
    args = _args()
    HOST  = args.host
    N     = args.n
    HOLD  = args.hold
    BASE  = f"http://{HOST}"
    WS    = f"ws://{HOST}"

    print(f"╔═══════════════════════════════════════════════════════════╗")
    print(f"║  SP-5b WebSocket Load Test                                ║")
    print(f"║  N={N}  hold={HOLD}s  host={HOST}")
    print(f"╚═══════════════════════════════════════════════════════════╝\n")

    m = Metrics(n=N)

    # Build candidate list
    cands = [
        Cand(idx=i, cccd=f"8{i:011d}", dev_id=str(uuid.uuid4()))
        for i in range(1, N + 1)
    ]

    # ── Phase 1: Login ─────────────────────────────────────────────────────
    print(f"[Phase 1] Logging in {N} candidates (concurrency={args.login_concurrency}) …")
    m.login_wall_s = await phase_login(cands, BASE, args.login_concurrency)
    ok_cands = [c for c in cands if c.login_ok]
    m.login_ok   = len(ok_cands)
    m.login_fail = N - m.login_ok
    print(f"  OK: {m.login_ok}/{N}  failed: {m.login_fail}  wall-time: {m.login_wall_s:.1f}s")

    if m.login_ok == 0:
        print("\nFATAL: 0 logins succeeded — check backend + setup_load.py")
        sys.exit(1)

    # ── Fetch admin token + sitting_id ────────────────────────────────────
    admin_token = await get_admin_token(BASE, args.proctor_user, args.proctor_pass)
    sitting_id  = await get_load_sitting_id(BASE, admin_token) if admin_token else None
    print(f"  Admin token: {'OK' if admin_token else 'FAIL'}")
    print(f"  Sitting ID:  {sitting_id or 'NOT FOUND'}")

    # ── Phase 2 + 3: Connect, hold, fanout ────────────────────────────────
    print(f"\n[Phase 2] Connecting {m.login_ok} WebSockets (hold={HOLD}s) …")
    await phase_connect_and_hold(ok_cands, WS, HOLD, m, admin_token, sitting_id, BASE)

    # ── Phase 4: Reconnect storm ───────────────────────────────────────────
    print(f"\n[Phase 4] Reconnect storm — reopening {m.login_ok} sockets immediately …")
    await phase_reconnect_storm(ok_cands, WS, m)
    pct = m.reconnect_ok / m.login_ok * 100 if m.login_ok else 0
    print(f"  Reconnect success: {m.reconnect_ok}/{m.login_ok} ({pct:.1f}%)")

    # ── Summary ───────────────────────────────────────────────────────────
    lats = sorted(m.fanout_latencies_ms)
    med  = lats[len(lats)//2]       if lats else None
    p95  = lats[int(len(lats)*0.95)] if lats else None

    print("\n" + "═" * 62)
    print("METRICS SUMMARY")
    print("═" * 62)
    print(f"  Logins          : {m.login_ok}/{N} OK  "
          f"({m.login_fail} failed)  wall={m.login_wall_s:.1f}s")
    print(f"  WS connects     : {m.ws_connect_ok}/{m.login_ok} OK  "
          f"({m.ws_connect_fail} failed)  "
          f"time-to-all={m.time_to_all_connected_s:.2f}s")
    print(f"  Hold duration   : {HOLD}s")
    print(f"  Messages rx'd   : {m.messages_received}")
    if m.fanout_done:
        fanout_str = (
            f"{m.fanout_receipt_count}/{m.ws_connect_ok} "
            f"({m.fanout_receipt_pct:.1f}%)"
        )
        lat_str = (
            f"  median={med:.1f}ms  P95={p95:.1f}ms"
            if med is not None else "  no latencies recorded"
        )
        print(f"  Fanout          : trigger={'OK' if m.fanout_triggered_ok else 'FAIL'}  "
              f"receipt={fanout_str}{lat_str}")
    else:
        print(f"  Fanout          : SKIPPED")
    pct_str = f"({m.reconnect_ok/m.login_ok*100:.1f}%)" if m.login_ok else ""
    print(f"  Reconnect storm : {m.reconnect_ok}/{m.login_ok} {pct_str}  "
          f"wall={m.reconnect_wall_s:.2f}s")
    print("═" * 62)


if __name__ == "__main__":
    asyncio.run(main())
