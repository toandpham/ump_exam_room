"""Bộ nạp QTI phải GIỮ số mũ / chỉ số dưới của đề (AD-127).

Thực địa 02-08: đề ghi bạch cầu ``12.5 x 10<sup>9</sup>/L`` nhưng màn thi hiện
``10 9/L`` dính liền thành **109/L** — sai hẳn về y khoa (10⁹ khác 109). Nguyên
nhân: ``_extract_blocks`` coi <sup>/<sub> là thẻ nội tuyến nên nối thẳng phần chữ
bên trong vào dòng, số mũ tụt xuống thành chữ số thường.

Cách sửa: đổi sang KÝ TỰ UNICODE mũ/chỉ số (10⁹, HCO₃⁻). Màn thi chạy chúng qua
``sciText`` (AD-122) → render thành <sup>/<sub> với chữ số ASCII nên KHÔNG phụ
thuộc glyph font của Windows 7.
"""

import xml.etree.ElementTree as ET

from app.services.qti_loader import _SUB_MAP, _SUP_MAP, _extract_text_and_images

# HỢP ĐỒNG 2 TẦNG — phải khớp bảng SUP/SUB trong `frontend-exam/src/lib/sciText.tsx`.
# Backend chỉ được sinh ký tự nằm trong tập này; màn thi đổi chúng sang <sup>/<sub>
# chữ số ASCII (không phụ thuộc font Windows 7). Thêm ký tự ở một bên mà quên bên
# kia → Win7 hiện ô vuông, đúng lỗi AD-122. Test bên kia: sciText.test.tsx.
RENDERABLE_SUP = set("0123456789+-=()n")
RENDERABLE_SUB = set("0123456789+-=()")


def _text(xml: str) -> str:
    return _extract_text_and_images(ET.fromstring(xml), "/tmp")[0]


def test_sup_becomes_unicode_superscript():
    # Đúng ca thực địa: 10 mũ 9 KHÔNG được dính thành "109".
    assert _text("<div>Bạch cầu: 12.5 x 10<sup>9</sup>/L</div>") == "Bạch cầu: 12.5 x 10⁹/L"


def test_sub_and_sup_combined():
    # Khí máu: HCO3- — chỉ số dưới rồi dấu điện tích ở trên.
    assert _text("<div>HCO<sub>3</sub><sup>-</sup>: 18 mmol/L</div>") == "HCO₃⁻: 18 mmol/L"


def test_multi_digit_exponent():
    assert _text("<p>Tiểu cầu 250 x 10<sup>12</sup>/L</p>") == "Tiểu cầu 250 x 10¹²/L"


def test_unmappable_script_falls_back_to_caret():
    """Chữ không có ký tự mũ Unicode (vd <sup>abc</sup>) → dùng ^ cho rõ nghĩa,
    tuyệt đối KHÔNG được nối phẳng vào dòng (đó chính là lỗi gốc)."""
    assert _text("<p>Diện tích cơ thể m<sup>abc</sup> đo được</p>") == "Diện tích cơ thể m^abc đo được"


def test_plain_text_unchanged():
    # Không có sup/sub → giữ nguyên (không phá đề cũ).
    assert _text("<p>Chọn <strong>đúng</strong> một đáp án.</p>") == "Chọn đúng một đáp án."


def test_backend_only_emits_characters_the_exam_screen_can_render():
    """Chốt ghép nối 2 tầng: mọi ký tự backend sinh ra phải nằm trong tập mà
    ``sciText`` đổi được sang <sup>/<sub> ASCII. Lệch một bên là Windows 7 hiện ô
    vuông (lỗi font AD-122) — mà lỗi đó chỉ lộ ra trên máy thi thật, không lộ ở đây."""
    assert set(_SUP_MAP) <= RENDERABLE_SUP, "ký tự mũ sciText.tsx chưa render được"
    assert set(_SUB_MAP) <= RENDERABLE_SUB, "ký tự chỉ số dưới sciText.tsx chưa render được"
