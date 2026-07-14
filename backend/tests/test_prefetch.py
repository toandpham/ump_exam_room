"""SP-2b: sau xác nhận (READY) tải được đề (trộn sẵn, ẩn đáp án) TRƯỚC khi Bắt đầu."""
import pytest
from app.models.enums import AdminRole
from tests.conftest import auth

pytestmark = pytest.mark.asyncio


async def test_questions_available_in_ready_before_start(client, factory):
    """Xác nhận xong → READY; /questions phục vụ ngay (prefetch) — ẩn đáp án, chưa có đồng hồ."""
    admin, ptok = await factory.admin(role=AdminRole.PROCTOR.value)
    # 6 câu để thấy có trộn.
    qs = [{"text": f"Câu {i}", "correct": "A"} for i in range(6)]
    exam, sitting, _ = await factory.active_exam(qs, owner_id=admin.id)
    cand = await factory.candidate(exam.id)
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd})).json()["token"]
    ch = auth(tok)
    # Xác nhận → READY (KHÔNG distribute, KHÔNG start).
    assert (await client.post("/api/exam/auth/confirm", headers=ch)).status_code == 200
    # Tải được đề NGAY ở READY (prefetch), ẩn đáp án đúng, chưa có đồng hồ.
    r = await client.get("/api/exam/questions", headers=ch)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["questions"]) == 6
    assert body["time_remaining_seconds"] is None
    assert all("correct_option" not in q for q in body["questions"])
    for q in body["questions"]:
        assert len(q["options"]) == 4


async def test_shuffle_preserved_per_candidate(client, factory):
    """Trộn câu + trộn đáp án vẫn hoạt động ở READY: 2 thí sinh khác thứ tự."""
    admin, ptok = await factory.admin(role=AdminRole.PROCTOR.value)
    qs = [{"text": f"Câu {i}", "correct": "A"} for i in range(8)]
    # shuffle=True: bật cả shuffle_questions + shuffle_options trong sitting (SP-2b Step 5).
    exam, sitting, _ = await factory.active_exam(qs, owner_id=admin.id, shuffle=True)

    async def order_for(_seed):
        c = await factory.candidate(exam.id)
        tok = (await client.post("/api/exam/auth/login", json={"cccd": c.cccd})).json()["token"]
        ch = auth(tok)
        await client.post("/api/exam/auth/confirm", headers=ch)
        body = (await client.get("/api/exam/questions", headers=ch)).json()
        q_order = [q["text"] for q in body["questions"]]
        opt_order = [o["id"] for o in body["questions"][0]["options"]]
        return q_order, opt_order

    o1q, o1o = await order_for(1)
    o2q, o2o = await order_for(2)
    assert len(o1q) == 8 and len(o1o) == 4
    # Ít nhất thứ tự câu HOẶC đáp án khác nhau giữa 2 thí sinh khi shuffle bật.
    assert (o1q != o2q) or (o1o != o2o)
