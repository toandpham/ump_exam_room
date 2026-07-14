"""Locust load test for the candidate exam path (AD-47 sitting model).

Run setup_load.py first to create N=1000 candidates + in_progress sessions:

  docker compose exec -T backend bash -c "cd /app && python -m load_tests.setup_load"

Then run Locust:

  docker run --rm --network app_thi_thu_default \\
    -v "$PWD/backend/load_tests:/mnt" locustio/locust \\
    -f /mnt/locustfile.py --host http://backend:8000 \\
    --headless -u 1000 -r 100 -t 120s

IMPORTANT: cleanup after the test (active exam blocks real exam creation):
  docker compose exec -T backend bash -c "cd /app && python -m load_tests.setup_load cleanup"

NOTE: Must run setup as `python -m load_tests.setup_load` (module mode) from /app so
Python resolves `app` from the project source, not the stale site-packages install.

Each virtual user sends:
  - Unique X-Device-Id (per-vUser uuid) → rate-limiter treats each as a distinct
    machine (AD-69: login rate is keyed by device-id first, not IP).
  - Unique X-Forwarded-For (random LAN IP) → mirrors real LAN traffic.

Hot-path tasks (steady-state after login):
  - weight 12 → POST /api/exam/answers  (BULK, AD-69 endpoint)
  - weight 2  → GET  /api/exam/state
"""

import itertools
import random
import uuid

from locust import HttpUser, between, task

N = 1000
_cccds = itertools.cycle(f"8{i:011d}" for i in range(1, N + 1))


class CandidateUser(HttpUser):
    wait_time = between(1, 4)
    questions: list[dict] = []

    def on_start(self) -> None:
        # Unique device-id → each vUser is an independent rate-limit bucket (AD-69).
        device_id = str(uuid.uuid4())
        self.client.headers.update({
            "X-Device-Id": device_id,
            "X-Forwarded-For": (
                f"10.{random.randint(0, 255)}."
                f"{random.randint(0, 255)}."
                f"{random.randint(1, 254)}"
            ),
        })

        cccd = next(_cccds)
        r = self.client.post(
            "/api/exam/auth/login",
            json={"cccd": cccd, "force": False},
            name="login",
        )
        self.questions = []
        if r.status_code != 200:
            return

        data = r.json()
        token = data.get("token")
        if not token:
            return
        self.client.headers["Authorization"] = f"Bearer {token}"

        qr = self.client.get("/api/exam/questions", name="questions")
        if qr.status_code == 200:
            self.questions = qr.json().get("questions", [])

    @task(12)
    def bulk_answers(self) -> None:
        """POST /api/exam/answers — bulk save a batch of answers."""
        if not self.questions:
            return
        # Send 3–8 answers in one request (realistic burst from client).
        batch_size = random.randint(3, min(8, len(self.questions)))
        batch = random.sample(self.questions, batch_size)
        answers = [
            {"question_id": q["id"], "selected_option": random.choice(["A", "B", "C", "D"])}
            for q in batch
        ]
        self.client.post(
            "/api/exam/answers",
            json={"answers": answers},
            name="answers",
        )

    @task(2)
    def poll_state(self) -> None:
        """GET /api/exam/state — heartbeat + timer poll."""
        self.client.get("/api/exam/state", name="state")
