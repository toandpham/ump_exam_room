"""AD-97: bộ nạp QTI phải GIỮ xuống dòng theo thẻ HTML của đề.

Đề của nhà cung cấp dùng <br/>, <p>, <div> để tách đoạn (vd phần "Xét nghiệm cận
lâm sàng"). Trước đây loader nối hết bằng dấu cách → dồn thành một dòng. Nay ranh
giới khối + <br/> thành \\n; màn thi render whitespace-pre-wrap nên xuống dòng đúng.
"""

import xml.etree.ElementTree as ET

from app.services.qti_loader import _extract_text_and_images

STEM = (
    '<div class="stem">Bệnh nhân nam 55 tuổi, test urease nhanh (+).'
    '<br/><div class="paraclinical-tests">'
    '<p><strong>Xét nghiệm cận lâm sàng:</strong></p>'
    '<p>Khí máu động mạch: pH 7.28.</p>'
    '<p>X-quang ngực: Phổi ứ khí.</p>'
    '</div></div>'
)


def test_block_and_br_become_line_breaks():
    text, _ = _extract_text_and_images(ET.fromstring(STEM), "/tmp")
    assert text.split("\n") == [
        "Bệnh nhân nam 55 tuổi, test urease nhanh (+).",
        "Xét nghiệm cận lâm sàng:",
        "Khí máu động mạch: pH 7.28.",
        "X-quang ngực: Phổi ứ khí.",
    ]


def test_plain_text_stays_single_line():
    # Câu không có thẻ khối → giữ nguyên 1 dòng (không phá đề cũ).
    text, _ = _extract_text_and_images(
        ET.fromstring('<div class="stem">Một dòng đơn giản.</div>'), "/tmp")
    assert text == "Một dòng đơn giản."


def test_inline_tags_do_not_add_breaks():
    # <strong>/<em> nội tuyến KHÔNG xuống dòng — chỉ thẻ khối + <br/> mới xuống.
    text, _ = _extract_text_and_images(
        ET.fromstring('<p>Chọn <strong>đúng</strong> một đáp án.</p>'), "/tmp")
    assert text == "Chọn đúng một đáp án."


def test_no_blank_lines_between_paragraphs():
    text, _ = _extract_text_and_images(
        ET.fromstring('<div><p>Dòng 1</p><p>Dòng 2</p></div>'), "/tmp")
    assert text == "Dòng 1\nDòng 2"


# --- AD-98: giữ đúng thứ tự chữ ↔ ảnh theo file QTI ---

def test_blocks_keep_image_position(monkeypatch):
    """Ảnh nằm GIỮA chữ (xét nghiệm → hình → câu hỏi) phải giữ đúng vị trí, không
    bị dồn xuống cuối."""
    monkeypatch.setattr("app.services.qti_loader._load_image",
                        lambda p: {"b64": "ZmFrZQ==", "mime": "image/jpeg"})
    from app.services.qti_loader import _extract_blocks
    xml = (
        '<div class="stem">Bệnh án + xét nghiệm.'
        '<br/><img src="resources/x.jpg" alt="Question attachment"/></div>'
    )
    blocks = _extract_blocks(ET.fromstring(xml), "/tmp")
    assert [b["type"] for b in blocks] == ["text", "image"]
    assert blocks[0]["text"] == "Bệnh án + xét nghiệm."


def test_extract_text_and_images_backward_compat(monkeypatch):
    """Hàm cũ vẫn trả (text, images) đúng — dùng cho đáp án + tương thích."""
    monkeypatch.setattr("app.services.qti_loader._load_image",
                        lambda p: {"b64": "ZmFrZQ==", "mime": "image/jpeg"})
    from app.services.qti_loader import _extract_text_and_images
    text, imgs = _extract_text_and_images(
        ET.fromstring('<div>A<br/><img src="r/x.jpg"/>B</div>'), "/tmp")
    assert text == "A\nB"
    assert len(imgs) == 1 and imgs[0]["mime"] == "image/jpeg"
