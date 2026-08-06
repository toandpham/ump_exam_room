"""Dự phòng giấy đầu-cuối: in phiếu → quét → đối chiếu → ghi vào CSDL (đợt 6).

Kịch bản thật: máy hỏng hàng loạt giữa buổi, phòng chuyển sang làm giấy. Điều quan
trọng nhất không phải là đọc được phiếu (đã có test riêng cho bộ đọc) mà là:

  - mã in trên phiếu phải ánh xạ về ĐÚNG thí sinh, kể cả khi danh sách thay đổi
    sau lúc in;
  - bước đọc và bước ghi phải TÁCH RỜI — máy đọc phiếu không bao giờ chắc chắn
    100%, nên chủ tịch phải xem rồi mới quyết;
  - bài làm trên MÁY luôn thắng bài giấy (nó có mốc thời gian + dấu niêm phong).
"""

import io

import pytest
from PIL import Image, ImageDraw

from app.services.omr import geometry as g
from tests.conftest import auth, fast_forward_start

DPI = 200
PX_PER_MM = DPI / 25.4

QUESTIONS = [{"text": f"Q{i}", "correct": "A"} for i in range(5)]


def _render(pdf: bytes, page: int) -> Image.Image:
    import pypdfium2
    doc = pypdfium2.PdfDocument(pdf)
    try:
        return doc[page].render(scale=DPI / 72).to_pil().convert("RGB")
    finally:
        doc.close()


def _fill(img: Image.Image, b: g.Bubble) -> None:
    d = ImageDraw.Draw(img)
    cx, cy = b.x_mm * PX_PER_MM, b.y_mm * PX_PER_MM
    r = g.BUBBLE_R_MM * PX_PER_MM * 0.85
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(20, 20, 20))


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def test_print_scan_apply_round_trip(client, factory, db):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    cand = await factory.candidate(exam.id)

    # 1. In phiếu — cũng là lúc ghi lại ánh xạ mã ↔ thí sinh.
    r = await client.get(f"/api/admin/sittings/{sitting.id}/paper/sheets.pdf",
                         headers=auth(ptok))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    pdf = r.content

    # 2. Thí sinh tô bài trên giấy.
    img = _render(pdf, 0)
    chosen = {0: "A", 1: "C", 2: "B"}
    for q, letter in chosen.items():
        _fill(img, g.option_bubbles(q)[g.OPTIONS.index(letter)])

    # 3. Quét → mới chỉ ĐỌC, chưa ghi gì.
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/paper/scan",
        files={"file": ("scan.png", _png(img), "image/png")}, headers=auth(ptok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_sheets"] == 1
    s = body["sheets"][0]
    assert s["cccd"] == cand.cccd, "mã trên phiếu phải về đúng thí sinh"
    assert s["answers"] == {"0": "A", "1": "C", "2": "B"}
    assert s["error"] is None

    from sqlalchemy import select
    from app.models import ExamSession
    assert await db.scalar(select(ExamSession).where(
        ExamSession.sitting_id == sitting.id)) is None, "bước quét không được ghi gì"

    # 4. Chủ tịch xác nhận → ghi + chấm.
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/paper/apply",
        json={"sheets": [{"candidate_id": s["candidate_id"],
                          "answers": {"0": "A", "1": "C", "2": "B"}}]},
        headers=auth(ptok))
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == 1

    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as fresh:
        sess = await fresh.scalar(select(ExamSession).where(
            ExamSession.sitting_id == sitting.id))
        assert sess.status == "submitted"
        assert sess.total_correct == 1, "chỉ câu 1 chọn A là đúng"
        assert sess.results_hash, "bài giấy cũng phải được niêm phong"


async def test_scan_refuses_when_sheets_were_never_printed(client, factory):
    """Không có ánh xạ thì mã trên phiếu là con số vô nghĩa — thà từ chối."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    await factory.candidate(exam.id)
    blank = Image.new("RGB", (400, 560), (255, 255, 255))

    r = await client.post(f"/api/admin/sittings/{sitting.id}/paper/scan",
                          files={"file": ("x.png", _png(blank), "image/png")},
                          headers=auth(ptok))
    assert r.status_code == 409
    assert "chưa in phiếu" in r.json()["detail"].lower()


async def test_unreadable_page_is_reported_not_silently_dropped(client, factory):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    await factory.candidate(exam.id)
    await client.get(f"/api/admin/sittings/{sitting.id}/paper/sheets.pdf", headers=auth(ptok))

    blank = Image.new("RGB", (800, 1100), (255, 255, 255))
    r = await client.post(f"/api/admin/sittings/{sitting.id}/paper/scan",
                          files={"file": ("x.png", _png(blank), "image/png")},
                          headers=auth(ptok))
    assert r.status_code == 200
    sheet = r.json()["sheets"][0]
    assert sheet["error"], "tờ đọc hỏng phải được báo, không được lặng lẽ bỏ qua"
    assert sheet["answers"] == {}


async def test_paper_never_overwrites_work_done_on_a_computer(client, factory, db):
    """Bài trên máy có mốc thời gian + niêm phong; bài giấy thì không."""
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    cand = await factory.candidate(exam.id)
    xff = {"X-Forwarded-For": "10.76.0.1"}
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd},
                             headers=xff)).json()["token"]
    ch = {**auth(tok), **xff}
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)
    await client.post("/api/exam/submit", headers=ch)

    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/paper/apply",
        json={"sheets": [{"candidate_id": str(cand.id), "answers": {"0": "A"}}]},
        headers=auth(ptok))
    assert r.status_code == 200
    assert r.json()["applied"] == 0
    assert "không ghi đè" in r.json()["skipped"][0]["reason"]


async def test_exam_paper_pdf_can_include_the_answer_key(client, factory):
    admin, ptok = await factory.admin()
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)

    plain = await client.get(f"/api/admin/sittings/{sitting.id}/paper/exam.pdf",
                             headers=auth(ptok))
    assert plain.status_code == 200 and plain.content[:4] == b"%PDF"

    keyed = await client.get(f"/api/admin/sittings/{sitting.id}/paper/exam.pdf"
                             "?with_answers=true", headers=auth(ptok))
    assert keyed.status_code == 200
    # Bản có đáp án phải TỰ NHẬN DẠNG được trong tên file — phát nhầm là lộ đề.
    assert "DAP AN" in keyed.headers.get("content-disposition", "")


async def test_paper_endpoints_are_owner_scoped(client, factory):
    admin, ptok = await factory.admin()
    _, other = await factory.admin()
    exam, sitting, _ = await factory.active_exam(QUESTIONS, owner_id=admin.id)
    for url in (f"/api/admin/sittings/{sitting.id}/paper/exam.pdf",
                f"/api/admin/sittings/{sitting.id}/paper/sheets.pdf"):
        assert (await client.get(url, headers=auth(other))).status_code == 404


@pytest.mark.parametrize("total,pages", [(1, 1), (100, 1), (101, 2), (280, 3)])
def test_sheet_count_matches_paper_length(total, pages):
    assert g.page_count(total) == pages
