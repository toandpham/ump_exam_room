"""AD-91: chỉ cho làm bài bằng phần mềm kiosk, trình duyệt thường bị chặn."""

import pytest

from app.config import settings
from app.core import kiosk_guard
from app.models.enums import AdminRole
from tests.conftest import auth

# UA thật của kiosk Electron 22 trên Windows 7 (bản đã phát cho trường).
KIOSK_UA = ("Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "exam-kiosk/1.2.0 Chrome/108.0.5359.215 Electron/22.3.27 Safari/537.36")
FIREFOX_UA = "Mozilla/5.0 (Windows NT 6.1; rv:115.0) Gecko/20100101 Firefox/115.0"
CHROME_UA = ("Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/109.0.0.0 Safari/537.36")


class _Req:
    """Request tối giản — chỉ cần headers cho hàm nhận diện."""
    def __init__(self, headers: dict):
        self.headers = {k.lower(): v for k, v in headers.items()}


def test_nhan_dien_kiosk_qua_user_agent():
    assert kiosk_guard.is_kiosk_request(_Req({"user-agent": KIOSK_UA}))


def test_nhan_dien_kiosk_qua_header_rieng():
    # Bản kiosk mới gửi header, không phụ thuộc User-Agent nữa.
    assert kiosk_guard.is_kiosk_request(_Req({"x-exam-kiosk": "1.3.0", "user-agent": FIREFOX_UA}))


@pytest.mark.parametrize("ua", [FIREFOX_UA, CHROME_UA, "", "curl/8.0"])
def test_trinh_duyet_thuong_khong_duoc_coi_la_kiosk(ua):
    assert not kiosk_guard.is_kiosk_request(_Req({"user-agent": ua}))


@pytest.fixture
def kiosk_only_on(monkeypatch):
    monkeypatch.setattr(settings, "kiosk_only", True)
    yield


@pytest.mark.asyncio
async def test_dang_nhap_bang_trinh_duyet_bi_chan(client, kiosk_only_on):
    r = await client.post("/api/exam/auth/login", json={"cccd": "079200000001"},
                          headers={"User-Agent": FIREFOX_UA})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "kiosk_required"


@pytest.mark.asyncio
async def test_man_cho_cua_thi_sinh_cung_bi_chan(client, kiosk_only_on):
    r = await client.get("/api/exam/auth/status", headers={"User-Agent": CHROME_UA})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "kiosk_required"


@pytest.mark.asyncio
async def test_kiosk_thi_qua_duoc(client, kiosk_only_on):
    r = await client.get("/api/exam/auth/status", headers={"User-Agent": KIOSK_UA})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_tat_co_thi_tro_lai_binh_thuong(client, monkeypatch):
    """Van xả KIOSK_ONLY=false — cho thi tạm bằng trình duyệt khi cần."""
    monkeypatch.setattr(settings, "kiosk_only", False)
    r = await client.get("/api/exam/auth/status", headers={"User-Agent": FIREFOX_UA})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_quan_tri_van_dung_trinh_duyet_binh_thuong(client, factory, kiosk_only_on):
    """Cổng chặn CHỈ gắn ở luồng thí sinh — chủ tịch/giám thị/quản trị vẫn làm
    việc trên Firefox/Chrome như thường."""
    _, token = await factory.admin(role=AdminRole.PROCTOR.value)
    r = await client.get("/api/admin/exams", headers={**auth(token), "User-Agent": FIREFOX_UA})
    assert r.status_code == 200
