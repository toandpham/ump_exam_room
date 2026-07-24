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
