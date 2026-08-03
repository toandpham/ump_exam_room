"""Ảnh nằm TRONG <sup>/<sub> không được biến mất (AD-132).

Hồi quy do chính bản vá số mũ AD-127: nhánh xử lý <sup>/<sub> lấy chữ bên trong rồi
``return`` luôn, KHÔNG duyệt tiếp thẻ con — nên đề viết
``<p><sub><img src="..."/></sub></p>`` bị mất sạch ảnh, im lặng, ở cả phần mềm thi
lẫn màn xem đề.

Đặt ảnh trong <sub> là cách viết lạ (bên soạn đề bọc nhầm), nhưng mất nội dung đề
thì không bao giờ được phép — thà hiển thị ảnh ở cỡ thường còn hơn không có gì.
"""

import xml.etree.ElementTree as ET

import pytest

import app.services.qti_loader as ql


@pytest.fixture(autouse=True)
def _fake_images(monkeypatch):
    monkeypatch.setattr(ql, "_load_image",
                        lambda p: {"b64": "ZmFrZQ==", "mime": "image/jpeg"})


def _kinds(xml: str):
    return [b["type"] for b in ql._extract_blocks(ET.fromstring(xml), "/tmp")]


def test_image_wrapped_in_sub_is_kept():
    assert _kinds('<div><p><sub><img src="resources/img_001.jpg" alt=""/></sub></p></div>') == ["image"]


def test_image_wrapped_in_sup_is_kept():
    assert _kinds('<div><p><sup><img src="a.jpg"/></sup></p></div>') == ["image"]


def test_image_in_sub_keeps_its_position_between_text():
    xml = ('<div class="stem"><p>Phần thân câu hỏi H<sub>2</sub>SO<sub>4</sub></p>'
           '<p><sub><img src="resources/img_001.jpg" alt=""/></sub></p>'
           '<p>Chẩn đoán nào sau đây là phù hợp nhất?</p></div>')
    blocks = ql._extract_blocks(ET.fromstring(xml), "/tmp")
    assert [b["type"] for b in blocks] == ["text", "image", "text"]
    # Chỉ số dưới của công thức vẫn đúng (không được phá bản vá AD-127).
    assert blocks[0]["text"] == "Phần thân câu hỏi H₂SO₄"
    assert blocks[2]["text"] == "Chẩn đoán nào sau đây là phù hợp nhất?"


def test_text_and_image_together_inside_sub():
    xml = '<div><p><sub>3<img src="a.jpg"/></sub></p></div>'
    blocks = ql._extract_blocks(ET.fromstring(xml), "/tmp")
    assert [b["type"] for b in blocks] == ["text", "image"]
    assert blocks[0]["text"] == "3"


def test_plain_script_still_converts():
    """Không có ảnh bên trong thì vẫn hạ/nâng chỉ số như cũ."""
    blocks = ql._extract_blocks(
        ET.fromstring("<p>Bạch cầu 10<sup>9</sup>/L, HCO<sub>3</sub></p>"), "/tmp")
    assert blocks[0]["text"] == "Bạch cầu 10⁹/L, HCO₃"
