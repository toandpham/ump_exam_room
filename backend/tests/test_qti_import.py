"""End-to-end test of the ONLY đề-loading path: a QTI 3.0 package encrypted as
.qenc uploaded into a sitting via ``POST /admin/sittings/{id}/import-qti`` (kèm
mã kích hoạt TOTP — spec 2026-07-13) then opened (AD-47). Exercises the whole
chain the conftest factory normally fakes — decrypt_qenc → _safe_extract_zip
→ qti_loader → _build_exam_file_from_qti (encrypt) → open → Redis push →
report_snapshot — then runs a candidate through it and checks the report + the
end-of-sitting purge.
"""

import io
import zipfile

import pyzipper
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Sitting
from tests.conftest import auth, fast_forward_start, qenc, qenc_code

MANIFEST = """<?xml version="1.0"?>
<manifest xmlns="http://www.imsglobal.org/xsd/imscp_v1p1">
  <resources>
    <resource type="imsqti_test_xmlv3p0" href="tests/test1.xml"/>
  </resources>
</manifest>
"""

TEST_XML = """<?xml version="1.0"?>
<qti-assessment-test title="TST QTI Exam">
  <qti-test-part>
    <qti-assessment-section identifier="s1">
      <qti-assessment-item-ref identifier="i1" href="../items/i1.xml"/>
      <qti-assessment-item-ref identifier="i2" href="../items/i2.xml"/>
    </qti-assessment-section>
  </qti-test-part>
</qti-assessment-test>
"""

ITEM = """<?xml version="1.0"?>
<qti-assessment-item identifier="{ident}">
  <qti-response-declaration identifier="RESPONSE" cardinality="single" base-type="identifier">
    <qti-correct-response><qti-value>A</qti-value></qti-correct-response>
  </qti-response-declaration>
  <qti-item-body>
    <p class="stem">Câu hỏi {ident}?</p>
    <qti-choice-interaction response-identifier="RESPONSE" shuffle="true" max-choices="1">
      <qti-simple-choice identifier="A">alpha</qti-simple-choice>
      <qti-simple-choice identifier="B">beta</qti-simple-choice>
      <qti-simple-choice identifier="C">gamma</qti-simple-choice>
      <qti-simple-choice identifier="D">delta</qti-simple-choice>
    </qti-choice-interaction>
  </qti-item-body>
</qti-assessment-item>
"""


def _build_qti_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("imsmanifest.xml", MANIFEST)
        zf.writestr("tests/test1.xml", TEST_XML)
        zf.writestr("items/i1.xml", ITEM.format(ident="i1"))
        zf.writestr("items/i2.xml", ITEM.format(ident="i2"))
    return buf.getvalue()


async def test_qti_import_then_full_candidate_flow(client, factory):
    admin, ptok = await factory.admin()
    exam, sitting = await factory.empty_active_exam(admin.id)

    # Upload the encrypted QTI package — the real import path.
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/import-qti",
        files={"file": ("exam.qenc", qenc(_build_qti_zip()), "application/octet-stream")},
        data={"code": qenc_code()},
        headers=auth(ptok),
    )
    assert r.status_code == 200, r.text
    assert r.json()["question_count"] == 2

    # Mở buổi → decrypt into Redis + flip active so candidates can log in.
    r = await client.post(f"/api/admin/sittings/{sitting.id}/open", headers=auth(ptok))
    assert r.status_code == 200 and r.json()["status"] == "active", r.text

    # Candidate runs the exam end-to-end.
    cand = await factory.candidate(exam.id)
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd})).json()["token"]
    ch = auth(tok)
    assert (await client.post("/api/exam/auth/confirm", headers=ch)).status_code == 200
    # SP-2b: confirm đặt READY; distribute bỏ qua.
    assert (await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))).json()["started"] == 1
    await fast_forward_start(sitting.id)  # SP-2c: bỏ qua đếm ngược để trả lời ngay

    qs = (await client.get("/api/exam/questions", headers=ch)).json()
    assert len(qs["questions"]) == 2
    assert all("correct_option" not in q for q in qs["questions"])  # answer key hidden

    # Option id "A" is the correct response for both items (loader maps the QTI
    # identifier A → letter A; shuffle reorders display, not the id).
    for q in qs["questions"]:
        assert (await client.post("/api/exam/answer",
                json={"question_id": q["id"], "selected_option": "A"}, headers=ch)).status_code == 200
    body = (await client.post("/api/exam/submit", headers=ch)).json()
    assert body["total"] == 2 and body["total_correct"] == 2

    # Report sees the submitted, fully-correct session (AD-68: new 2-sheet structure).
    rep = (await client.get(f"/api/admin/sittings/{sitting.id}/report", headers=auth(ptok))).json()
    assert rep["meta"]["question_count"] == 2
    submitted_rows = [r for r in rep["rows"] if r["status"] in ("submitted", "timeout")]
    assert len(submitted_rows) == 1
    assert submitted_rows[0]["total_correct"] == 2
    # Cả 2 câu đều chọn đúng A
    assert submitted_rows[0]["answers"] == ["A", "A"]

    # Đóng buổi → purge payload + close. report_snapshot survives.
    assert (await client.post(f"/api/admin/sittings/{sitting.id}/end", headers=auth(ptok))).status_code == 200
    detail = (await client.get(f"/api/admin/sittings/{sitting.id}", headers=auth(ptok))).json()
    assert detail["status"] == "closed"
    # Questions can no longer be served (no open sitting → payload gone).
    assert (await client.get("/api/exam/questions", headers=ch)).status_code == 409


async def test_import_forces_shuffle_on(client, factory):
    """AD-69: import LUÔN bật đảo câu hỏi + đảo đáp án, bất kể file QTI khai gì."""
    admin, ptok = await factory.admin()
    exam, sitting = await factory.empty_active_exam(admin.id)
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/import-qti",
        files={"file": ("exam.qenc", qenc(_build_qti_zip()), "application/octet-stream")},
        data={"code": qenc_code()}, headers=auth(ptok),
    )
    assert r.status_code == 200, r.text
    async with AsyncSessionLocal() as db:
        s = await db.scalar(select(Sitting).where(Sitting.id == sitting.id))
        assert s.shuffle_questions is True
        assert s.shuffle_options is True


async def test_bulk_answers_then_score(client, factory):
    """AD-69: client gộp đáp án đẩy 1 lần qua /exam/answers; chấm điểm đúng."""
    admin, ptok = await factory.admin()
    exam, sitting = await factory.empty_active_exam(admin.id)
    await client.post(f"/api/admin/sittings/{sitting.id}/import-qti",
                      files={"file": ("exam.qenc", qenc(_build_qti_zip()), "application/octet-stream")},
                      data={"code": qenc_code()}, headers=auth(ptok))
    await client.post(f"/api/admin/sittings/{sitting.id}/open", headers=auth(ptok))
    cand = await factory.candidate(exam.id)
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd})).json()["token"]
    ch = auth(tok)
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)  # SP-2c: bỏ qua đếm ngược để trả lời ngay
    qs = (await client.get("/api/exam/questions", headers=ch)).json()["questions"]

    # Gộp cả 2 đáp án vào 1 request.
    r = await client.post("/api/exam/answers", headers=ch, json={
        "answers": [{"question_id": q["id"], "selected_option": "A"} for q in qs]})
    assert r.status_code == 200, r.text
    assert r.json()["saved"] == 2
    body = (await client.post("/api/exam/submit", headers=ch)).json()
    assert body["total"] == 2 and body["total_correct"] == 2


async def test_import_qti_rejects_plain_zip(client, factory):
    """ZIP thường (chưa mã hoá bằng tool) → 400, kể cả kèm mã đúng."""
    admin, ptok = await factory.admin()
    exam, sitting = await factory.empty_active_exam(admin.id)
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/import-qti",
        files={"file": ("exam.zip", _build_qti_zip(), "application/zip")},
        data={"code": qenc_code()},
        headers=auth(ptok),
    )
    assert r.status_code == 400
    assert "mã hoá" in r.json()["detail"].lower()


async def test_import_qti_rejects_garbage_file(client, factory):
    admin, ptok = await factory.admin()
    exam, sitting = await factory.empty_active_exam(admin.id)
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/import-qti",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"code": qenc_code()},
        headers=auth(ptok),
    )
    assert r.status_code == 400


async def test_import_qti_rejects_wrong_code(client, factory):
    """Mã kích hoạt sai/hết hạn → 400, KHÔNG giải mã file."""
    admin, ptok = await factory.admin()
    exam, sitting = await factory.empty_active_exam(admin.id)
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/import-qti",
        files={"file": ("exam.qenc", qenc(_build_qti_zip()), "application/octet-stream")},
        data={"code": "00000000"},
        headers=auth(ptok),
    )
    assert r.status_code == 400
    assert "kích hoạt" in r.json()["detail"].lower()


async def test_import_qti_rejects_tampered_qenc(client, factory):
    """File .qenc bị sửa (GCM tag lệch) → 400."""
    admin, ptok = await factory.admin()
    exam, sitting = await factory.empty_active_exam(admin.id)
    bad = bytearray(qenc(_build_qti_zip()))
    bad[-1] ^= 0xFF
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/import-qti",
        files={"file": ("exam.qenc", bytes(bad), "application/octet-stream")},
        data={"code": qenc_code()},
        headers=auth(ptok),
    )
    assert r.status_code == 400
    assert "hỏng" in r.json()["detail"].lower()


async def test_import_qti_inner_zip_with_password_rejected(client, factory):
    """ZIP bên trong .qenc còn đặt mật khẩu supplier → 400 hướng dẫn nén lại."""
    buf = io.BytesIO()
    with pyzipper.AESZipFile(buf, "w", compression=pyzipper.ZIP_DEFLATED,
                             encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(b"supplier-pw")
        zf.writestr("imsmanifest.xml", MANIFEST)
    admin, ptok = await factory.admin()
    exam, sitting = await factory.empty_active_exam(admin.id)
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/import-qti",
        files={"file": ("exam.qenc", qenc(buf.getvalue()), "application/octet-stream")},
        data={"code": qenc_code()},
        headers=auth(ptok),
    )
    assert r.status_code == 400
    assert "mật khẩu" in r.json()["detail"].lower()
