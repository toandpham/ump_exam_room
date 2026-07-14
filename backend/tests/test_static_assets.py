"""SP-1: materialize ảnh đề ra file tĩnh + wipe (exam_assets)."""

import base64
import io
import uuid
import zipfile
from pathlib import Path

import pytest

from app.services import exam_assets
from tests.conftest import auth, qenc, qenc_code

# 1x1 PNG hợp lệ (đủ để decode + ghi file).
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_PNG_B64 = base64.b64encode(_PNG).decode("ascii")


@pytest.fixture()
def upload_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(exam_assets.settings, "upload_dir", str(tmp_path))
    return tmp_path


def _payload_with_image() -> dict:
    return {
        "questions": [
            {
                "id": "q1", "text": "Câu 1",
                "images": [{"b64": _PNG_B64, "mime": "image/png"}],
                "options": [
                    {"id": "A", "text": "a", "images": [{"b64": _PNG_B64, "mime": "image/png"}]},
                    {"id": "B", "text": "b", "images": []},
                ],
            },
            {"id": "q2", "text": "Câu 2 không ảnh", "images": [], "options": []},
        ]
    }


def test_materialize_writes_files_and_sets_url(upload_tmp):
    sid = uuid.uuid4()
    payload = exam_assets.materialize_payload_images(sid, _payload_with_image())

    q1 = payload["questions"][0]
    url = q1["images"][0]["url"]
    assert url.startswith(f"/uploads/sitting_{sid.hex}/img/")
    assert url.endswith(".png")
    # File tồn tại đúng vị trí Caddy phục vụ.
    rel = url[len("/uploads/"):]
    assert (upload_tmp / rel).is_file()
    # Option ảnh cũng có url.
    assert q1["options"][0]["images"][0]["url"].endswith(".png")
    # Option/câu không ảnh → không thêm gì, không lỗi.
    assert q1["options"][1]["images"] == []
    assert payload["questions"][1]["images"] == []


def test_materialize_strips_b64_after_writing(upload_tmp):
    """SP-1b: ảnh đã ra file tĩnh thì XOÁ b64 khỏi payload — bản ghi vào Redis
    chỉ còn URL (đề 280 câu nhiều ảnh từng phình Redis payload ~110MB, mỗi lần
    /questions kéo cả blob → lag khi máy mới đăng nhập giữa buổi 13-07)."""
    sid = uuid.uuid4()
    payload = exam_assets.materialize_payload_images(sid, _payload_with_image())
    q1 = payload["questions"][0]
    assert "b64" not in q1["images"][0]
    assert "b64" not in q1["options"][0]["images"][0]
    # URL + file tĩnh vẫn đầy đủ.
    url = q1["images"][0]["url"]
    assert (upload_tmp / url[len("/uploads/"):]).is_file()


def test_materialize_keeps_b64_when_image_broken(upload_tmp):
    """Ảnh hỏng (không decode được) → giữ nguyên dict để /questions còn đường
    fallback data URL, không chặn cả buổi."""
    sid = uuid.uuid4()
    payload = {"questions": [{
        "id": "q", "text": "x",
        "images": [{"b64": "!!!không-phải-base64", "mime": "image/png"}],
        "options": [],
    }]}
    out = exam_assets.materialize_payload_images(sid, payload)
    im = out["questions"][0]["images"][0]
    assert "url" not in im
    assert im["b64"] == "!!!không-phải-base64"


def test_materialize_dedups_identical_bytes(upload_tmp):
    sid = uuid.uuid4()
    exam_assets.materialize_payload_images(sid, _payload_with_image())
    img_dir = upload_tmp / f"sitting_{sid.hex}" / "img"
    # Câu + option dùng CÙNG bytes PNG → chỉ 1 file (dedup theo sha256).
    assert len(list(img_dir.glob("*.png"))) == 1


def test_materialize_idempotent(upload_tmp):
    sid = uuid.uuid4()
    exam_assets.materialize_payload_images(sid, _payload_with_image())
    # Gọi lại không lỗi (file đã tồn tại → bỏ qua ghi).
    payload = exam_assets.materialize_payload_images(sid, _payload_with_image())
    assert payload["questions"][0]["images"][0]["url"].endswith(".png")


def test_wipe_removes_dir(upload_tmp):
    sid = uuid.uuid4()
    exam_assets.materialize_payload_images(sid, _payload_with_image())
    d = upload_tmp / f"sitting_{sid.hex}"
    assert d.exists()
    assert exam_assets.wipe_sitting_assets(sid) is True
    assert not d.exists()
    # Wipe lần 2 (đã xoá) → False, không lỗi.
    assert exam_assets.wipe_sitting_assets(sid) is False


_MANIFEST = """<?xml version="1.0"?>
<manifest xmlns="http://www.imsglobal.org/xsd/imscp_v1p1">
  <resources><resource type="imsqti_test_xmlv3p0" href="tests/test1.xml"/></resources>
</manifest>"""

_TEST_XML = """<?xml version="1.0"?>
<qti-assessment-test title="IMG QTI">
  <qti-test-part><qti-assessment-section identifier="s1">
    <qti-assessment-item-ref identifier="i1" href="../items/i1.xml"/>
  </qti-assessment-section></qti-test-part>
</qti-assessment-test>"""

# Ảnh src giải theo PACKAGE ROOT (qti_loader: os.path.join(root_dir, src)).
_ITEM_IMG = """<?xml version="1.0"?>
<qti-assessment-item identifier="i1">
  <qti-response-declaration identifier="RESPONSE" cardinality="single" base-type="identifier">
    <qti-correct-response><qti-value>A</qti-value></qti-correct-response>
  </qti-response-declaration>
  <qti-item-body>
    <p class="stem">Câu có ảnh <img src="resources/pic.png" alt="hinh"/></p>
    <qti-choice-interaction response-identifier="RESPONSE" shuffle="true" max-choices="1">
      <qti-simple-choice identifier="A">alpha</qti-simple-choice>
      <qti-simple-choice identifier="B">beta</qti-simple-choice>
      <qti-simple-choice identifier="C">gamma</qti-simple-choice>
      <qti-simple-choice identifier="D">delta</qti-simple-choice>
    </qti-choice-interaction>
  </qti-item-body>
</qti-assessment-item>"""


def _qti_zip_with_image() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("imsmanifest.xml", _MANIFEST)
        zf.writestr("tests/test1.xml", _TEST_XML)
        zf.writestr("items/i1.xml", _ITEM_IMG)
        zf.writestr("resources/pic.png", _PNG)
    return buf.getvalue()


async def test_questions_serve_static_url_then_wiped(client, factory):
    admin, ptok = await factory.admin()
    exam, sitting = await factory.empty_active_exam(admin.id)
    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/import-qti",
        files={"file": ("exam.qenc", qenc(_qti_zip_with_image()), "application/octet-stream")},
        data={"code": qenc_code()}, headers=auth(ptok),
    )
    assert r.status_code == 200, r.text
    assert (await client.post(f"/api/admin/sittings/{sitting.id}/open", headers=auth(ptok))).status_code == 200

    cand = await factory.candidate(exam.id)
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd})).json()["token"]
    ch = auth(tok)
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))

    qs = (await client.get("/api/exam/questions", headers=ch)).json()["questions"]
    imgs = [u for q in qs for u in q["images"]]
    assert imgs, "câu phải có ảnh"
    # alt của ảnh ("hinh") KHÔNG được nhét vào nội dung câu hỏi (tránh dòng rác).
    assert all("hinh" not in q["text"] for q in qs)
    # SP-1: ảnh là URL tĩnh, KHÔNG phải data URL base64.
    assert all(u.startswith(f"/uploads/sitting_{sitting.id.hex}/img/") for u in imgs)
    assert not any(u.startswith("data:") for u in imgs)
    # File thật nằm trên đĩa nơi Caddy phục vụ.
    from app.config import settings
    rel = imgs[0][len("/uploads/"):]
    assert (Path(settings.upload_dir) / rel).is_file()
    # Đáp án đúng vẫn không lộ.
    assert all("correct_option" not in q for q in qs)

    # Đóng buổi → ảnh tĩnh bị xoá sạch.
    assert (await client.post(f"/api/admin/sittings/{sitting.id}/end", headers=auth(ptok))).status_code == 200
    assert not (Path(settings.upload_dir) / f"sitting_{sitting.id.hex}").exists()


def test_images_falls_back_to_base64_when_no_url():
    """Payload cũ chưa materialize (không có 'url') → /questions vẫn trả data URL."""
    from app.api.exam.answer import _images
    out = _images({"images": [{"b64": _PNG_B64, "mime": "image/png"}]})
    assert len(out) == 1
    assert out[0].startswith("data:image/png;base64,")
    # Khi CÓ url thì ưu tiên url.
    out2 = _images({"images": [{"b64": _PNG_B64, "mime": "image/png", "url": "/uploads/x/y.png"}]})
    assert out2 == ["/uploads/x/y.png"]
