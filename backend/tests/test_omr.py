"""Phiếu trả lời giấy: in ra rồi đọc lại (đợt 6).

Không có máy quét trên máy phát triển, nên kiểm chứng bằng vòng tròn KHÉP KÍN:
in phiếu thật (PDF) → dựng thành ảnh như máy quét → tô ô bằng mã → làm bẩn ảnh
(xoay, nhiễu, mờ, lệch sáng) → cho bộ đọc đọc → so với đáp án đã tô.

Cách này bắt được đúng loại lỗi nguy hiểm nhất: bên in và bên đọc hiểu hình học
khác nhau. Nó KHÔNG thay được một lần nghiệm thu với máy quét thật — giấy thật
còn có bụi, nếp gấp, mực lem — và điều đó phải nói rõ trước khi tin dùng.
"""

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from app.services.omr import geometry as g
from app.services.omr import reader, sheet

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

DPI = 200
PX_PER_MM = DPI / 25.4


def _render(pdf: bytes, page: int) -> Image.Image:
    import pypdfium2
    doc = pypdfium2.PdfDocument(pdf)
    try:
        return doc[page].render(scale=DPI / 72).to_pil().convert("RGB")
    finally:
        doc.close()


def _fill(img: Image.Image, x_mm: float, y_mm: float) -> None:
    """Tô đen một bóng, như thí sinh dùng bút chì."""
    d = ImageDraw.Draw(img)
    cx, cy = x_mm * PX_PER_MM, y_mm * PX_PER_MM
    r = g.BUBBLE_R_MM * PX_PER_MM * 0.85
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(20, 20, 20))


def _sheets(total_questions: int, index: int = 1234) -> bytes:
    return sheet.build_answer_sheets(
        font="Helvetica", exam_name="Kỳ thi thử", sitting_name="Buổi 1",
        candidates=[{"index": index, "cccd": "079200001234",
                     "full_name": "Nguyen Van Test", "room_name": "Phong 1"}],
        total_questions=total_questions,
    )


def test_geometry_is_one_source_of_truth():
    """Đây là hợp đồng giữa bên in và bên đọc — lệch một milimét là hỏng cả tờ."""
    assert g.page_count(100) == 1
    assert g.page_count(101) == 2
    assert g.page_count(280) == 3
    assert g.questions_on_page(280, 2) == list(range(200, 280))
    assert g.decode_bits(g.encode_bits(1234, g.ID_BITS)) == 1234
    assert g.decode_bits(g.encode_bits(0, g.ID_BITS)) == 0
    # Bốn bóng của một câu phải cùng hàng và cách đều nhau.
    bs = g.option_bubbles(0)
    assert len({round(b.y_mm, 6) for b in bs}) == 1
    gaps = [round(b2.x_mm - b1.x_mm, 6) for b1, b2 in zip(bs, bs[1:])]
    assert len(set(gaps)) == 1


def test_round_trip_reads_back_exactly_what_was_filled():
    total = 40
    pdf = _sheets(total)
    img = _render(pdf, 0)
    chosen = {i: g.OPTIONS[i % 4] for i in range(total)}
    for i, letter in chosen.items():
        b = g.option_bubbles(i)[g.OPTIONS.index(letter)]
        _fill(img, b.x_mm, b.y_mm)

    res = reader.read_sheet(img, total)
    assert res.candidate_index == 1234
    assert res.page == 0
    assert res.answers == chosen
    assert res.unsure == []


def test_blank_sheet_reads_as_no_answers_not_as_guesses():
    """Bóng in sẵn có viền — bộ đọc không được coi viền là 'đã tô'."""
    total = 20
    res = reader.read_sheet(_render(_sheets(total), 0), total)
    assert res.answers == {}
    assert res.unsure == []
    assert res.candidate_index == 1234


def test_survives_a_crooked_noisy_scan():
    """Đặt lệch trên mặt kính + ảnh nhiễu, mờ, ngả xám — vẫn phải đọc đúng."""
    total = 30
    img = _render(_sheets(total), 0)
    chosen = {i: g.OPTIONS[(i * 3) % 4] for i in range(total)}
    for i, letter in chosen.items():
        b = g.option_bubbles(i)[g.OPTIONS.index(letter)]
        _fill(img, b.x_mm, b.y_mm)

    # Xoay 1,5° quanh tâm, nền trắng; rồi mờ nhẹ + nhiễu hạt + tối đi một chút.
    img = img.rotate(1.5, resample=Image.BICUBIC, fillcolor=(255, 255, 255), expand=True)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    arr = np.asarray(img).astype(np.int16)
    rng = np.random.default_rng(7)
    arr = np.clip(arr * 0.92 + rng.normal(0, 9, arr.shape), 0, 255).astype(np.uint8)

    res = reader.read_sheet(Image.fromarray(arr), total)
    assert res.candidate_index == 1234
    assert res.answers == chosen


def test_double_marked_question_is_flagged_not_guessed():
    """Tô hai ô: máy KHÔNG được chọn bừa một cái — chấm sai còn tệ hơn nhập tay."""
    total = 10
    img = _render(_sheets(total), 0)
    for b in (g.option_bubbles(3)[0], g.option_bubbles(3)[2]):
        _fill(img, b.x_mm, b.y_mm)
    _fill(img, *(lambda b: (b.x_mm, b.y_mm))(g.option_bubbles(5)[1]))

    res = reader.read_sheet(img, total)
    assert 3 in res.unsure
    assert 3 not in res.answers
    assert res.answers.get(5) == "B", "câu tô đúng một ô vẫn phải đọc được"


def test_reads_the_second_page_of_a_long_paper():
    """Đề 280 câu chia 3 tờ — số tờ phải đọc được, nếu không thì ghép sai câu."""
    total = 280
    pdf = _sheets(total)
    img = _render(pdf, 1)                     # tờ thứ hai
    q = 150                                   # câu 151, nằm ở tờ 2
    i_on_page = q - g.QUESTIONS_PER_PAGE
    _fill(img, *(lambda b: (b.x_mm, b.y_mm))(g.option_bubbles(i_on_page)[3]))

    res = reader.read_sheet(img, total)
    assert res.page == 1
    assert res.answers == {q: "D"}


def test_missing_fiducials_is_an_error_not_a_wrong_answer():
    """Ảnh không phải phiếu (chụp nhầm, tờ khác) → báo lỗi, tuyệt đối không đoán."""
    blank = Image.new("RGB", (800, 1100), (255, 255, 255))
    with pytest.raises(reader.OmrError):
        reader.read_sheet(blank, 20)


def test_pdf_upload_is_split_into_pages():
    pdf = _sheets(280)
    imgs = reader.images_from_upload(pdf, "scan.pdf")
    assert len(imgs) == 3, "một thí sinh, đề 280 câu → 3 tờ"
