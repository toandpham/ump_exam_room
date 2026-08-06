"""In phiếu trả lời giấy (dự phòng khi máy hỏng hàng loạt).

Dùng chung hình học với bộ đọc (``geometry``) nên hai bên không thể lệch nhau.
"""

from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from . import geometry as g


def _y(y_mm: float) -> float:
    """Đổi trục: hình học đếm y từ TRÊN xuống, reportlab đếm từ DƯỚI lên."""
    return (g.PAGE_H_MM - y_mm) * mm


def _draw_fiducials(c: canvas.Canvas) -> None:
    c.setFillGray(0)
    half = g.FIDUCIAL_SIZE_MM / 2
    for x_mm, y_mm in g.FIDUCIALS_MM:
        c.rect((x_mm - half) * mm, _y(y_mm + half),
               g.FIDUCIAL_SIZE_MM * mm, g.FIDUCIAL_SIZE_MM * mm, stroke=0, fill=1)


def _draw_bubble(c: canvas.Canvas, b: g.Bubble, label: str = "") -> None:
    c.setLineWidth(0.6)
    c.setStrokeGray(0.35)
    c.setFillGray(1)
    c.circle(b.x_mm * mm, _y(b.y_mm), g.BUBBLE_R_MM * mm, stroke=1, fill=1)
    if label:
        c.setFillGray(0.45)
        c.setFont("Helvetica", 5)
        c.drawCentredString(b.x_mm * mm, _y(b.y_mm) - 1.6, label)


def _draw_filled(c: canvas.Canvas, b: g.Bubble) -> None:
    """Tô đen một bóng — dùng cho mã thí sinh / số tờ do máy in sẵn."""
    c.setFillGray(0)
    c.circle(b.x_mm * mm, _y(b.y_mm), g.BUBBLE_R_MM * mm, stroke=0, fill=1)


def build_answer_sheets(
    *,
    font: str,
    exam_name: str,
    sitting_name: str,
    candidates: list[dict],
    total_questions: int,
) -> bytes:
    """Phiếu trả lời cho từng thí sinh (mỗi người vài tờ nếu đề dài).

    ``candidates``: [{"index": int, "cccd": str, "full_name": str, "room_name": str}]
    — ``index`` là mã nhị phân in trên tờ, do bên gọi cấp và giữ để ánh xạ ngược.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    pages = g.page_count(total_questions)

    for cand in candidates:
        for page in range(pages):
            _draw_fiducials(c)

            c.setFillGray(0)
            c.setFont(font, 11)
            c.drawString(g.CODE_X0_MM * mm, _y(26), f"{exam_name} — {sitting_name}")
            c.setFont(font, 13)
            c.drawString(g.CODE_X0_MM * mm, _y(33), cand["full_name"])
            c.setFont(font, 10)
            c.drawString(g.CODE_X0_MM * mm, _y(39),
                         f"Số báo danh: {cand['cccd']}"
                         + (f"   ·   Phòng: {cand['room_name']}" if cand.get("room_name") else "")
                         + f"   ·   Tờ {page + 1}/{pages}")

            # Mã thí sinh + số tờ (máy in sẵn — thí sinh không tô).
            c.setFont("Helvetica", 6)
            c.setFillGray(0.45)
            c.drawRightString((g.CODE_X0_MM - 2) * mm, _y(g.ID_ROW_Y_MM) - 1.8, "MÃ")
            c.drawRightString((g.CODE_X0_MM - 2) * mm, _y(g.PAGE_ROW_Y_MM) - 1.8, "TỜ")
            for b, on in zip(g.id_bubbles(), g.encode_bits(cand["index"], g.ID_BITS)):
                _draw_filled(c, b) if on else _draw_bubble(c, b)
            for b, on in zip(g.page_bubbles(), g.encode_bits(page, g.PAGE_BITS)):
                _draw_filled(c, b) if on else _draw_bubble(c, b)

            # Lưới đáp án.
            qs = g.questions_on_page(total_questions, page)
            for i, q_index in enumerate(qs):
                x0, y = g.question_slot(i)
                c.setFillGray(0)
                c.setFont(font, 9)
                c.drawRightString((x0 + g.NUM_W_MM - 4) * mm, _y(y) - 2.2, str(q_index + 1))
                for b, letter in zip(g.option_bubbles(i), g.OPTIONS):
                    _draw_bubble(c, b, letter)

            c.setFont(font, 7)
            c.setFillGray(0.45)
            c.drawString(45 * mm, _y(g.PAGE_H_MM - 20),
                         "Tô ĐẬM KÍN một ô cho mỗi câu bằng bút chì/bút bi đen. "
                         "Không viết vào bốn ô vuông đen ở góc.")
            c.showPage()

    c.save()
    return buf.getvalue()
