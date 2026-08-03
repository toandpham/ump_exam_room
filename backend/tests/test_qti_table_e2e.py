"""Bảng của đề đi trọn chuỗi tới máy thí sinh (AD-129).

Test khối đơn lẻ chỉ chứng minh bộ nạp đọc đúng. Test này chạy ĐÚNG đường thật —
nạp gói QTI đã mã hoá → mở buổi (mã hoá at-rest, nạp Redis, materialize ảnh) →
thí sinh gọi /exam/questions — để chắc bảng không bị rơi ở khâu nào giữa đường.

XML chép nguyên cấu trúc nhà cung cấp dùng trong đề 001 (thực địa 03-08).
"""

import io
import zipfile

import pytest

from tests.conftest import auth, fast_forward_start, qenc, QENC_PASSWORD

pytestmark = pytest.mark.asyncio

MANIFEST = """<?xml version="1.0"?>
<manifest xmlns="http://www.imsglobal.org/xsd/imscp_v1p1">
  <resources><resource type="imsqti_test_xmlv3p0" href="tests/t.xml"/></resources>
</manifest>
"""

TEST_XML = """<?xml version="1.0"?>
<qti-assessment-test title="Đề có bảng">
  <qti-test-part><qti-assessment-section identifier="s1">
    <qti-assessment-item-ref identifier="i1" href="../items/i1.xml"/>
  </qti-assessment-section></qti-test-part>
</qti-assessment-test>
"""

ITEM = """<?xml version="1.0"?>
<qti-assessment-item identifier="i1">
  <qti-response-declaration identifier="RESPONSE" cardinality="single" base-type="identifier">
    <qti-correct-response><qti-value>A</qti-value></qti-correct-response>
  </qti-response-declaration>
  <qti-item-body>
    <div class="stem"><p>Khí máu động mạch: pH 7.28, bạch cầu 12 x 10<sup>9</sup>/L.</p>
    <table style="border-collapse:collapse"><tbody>
      <tr><td><strong>A</strong></td><td><strong>B</strong></td><td><strong>C</strong></td></tr>
      <tr><td>1</td><td>3</td><td>5</td></tr>
      <tr><td>2</td><td>4</td><td>6</td></tr>
    </tbody></table>
    <p>Thái độ xử trí ban đầu nào là phù hợp nhất?</p></div>
    <qti-choice-interaction response-identifier="RESPONSE" shuffle="true" max-choices="1">
      <qti-simple-choice identifier="A">alpha</qti-simple-choice>
      <qti-simple-choice identifier="B">beta</qti-simple-choice>
      <qti-simple-choice identifier="C">gamma</qti-simple-choice>
      <qti-simple-choice identifier="D">delta</qti-simple-choice>
    </qti-choice-interaction>
  </qti-item-body>
</qti-assessment-item>
"""


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("imsmanifest.xml", MANIFEST)
        zf.writestr("tests/t.xml", TEST_XML)
        zf.writestr("items/i1.xml", ITEM)
    return buf.getvalue()


async def test_table_reaches_the_candidate_screen(client, factory):
    admin, ptok = await factory.admin()
    exam, sitting = await factory.empty_active_exam(admin.id)

    r = await client.post(
        f"/api/admin/sittings/{sitting.id}/import-qti",
        files={"file": ("de.qenc", qenc(_zip()), "application/octet-stream")},
        data={"password": QENC_PASSWORD},
        headers=auth(ptok))
    assert r.status_code == 200, r.text
    assert (await client.post(f"/api/admin/sittings/{sitting.id}/open",
                              headers=auth(ptok))).status_code == 200

    cand = await factory.candidate(exam.id)
    tok = (await client.post("/api/exam/auth/login", json={"cccd": cand.cccd})).json()["token"]
    ch = auth(tok)
    await client.post("/api/exam/auth/confirm", headers=ch)
    await client.post(f"/api/admin/sittings/{sitting.id}/start", headers=auth(ptok))
    await fast_forward_start(sitting.id)

    q = (await client.get("/api/exam/questions", headers=ch)).json()["questions"][0]
    kinds = [b["type"] for b in q["blocks"]]
    assert kinds == ["text", "table", "text"], q["blocks"]

    table = q["blocks"][1]
    assert table["rows"] == [["A", "B", "C"], ["1", "3", "5"], ["2", "4", "6"]]
    assert table["header"] is True
    # Số mũ đi cùng chuyến (AD-127) — máy thí sinh đổi sang <sup> ASCII khi vẽ.
    assert "10⁹/L" in q["blocks"][0]["text"]
