"""Dự phòng giấy: in đề ra PDF + phát phiếu trả lời + nhận bản quét (đợt 6).

Dành cho tình huống máy hỏng hàng loạt giữa buổi — đã xảy ra với 320 máy Win7. Đề
lấy từ ``sitting.report_snapshot`` (ghi lúc nạp đề, sống sót cả sau khi đề bị xoá),
ảnh lấy từ file tĩnh đã materialize.

Bản in theo **thứ tự gốc của đề** cho cả phòng — không trộn theo từng thí sinh:
thi giấy thì giám thị coi trực tiếp, mà một bản chung thì in và soát dễ hơn nhiều.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from app.config import settings
from app.services.seating_service import _FONT, _FONT_BOLD

logger = logging.getLogger("exam.paper")

# Ảnh in ra giấy: rộng tối đa 120mm để không tràn khổ và không làm file phình.
MAX_IMG_W_MM = 120.0


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br/>"))


def _image_path(url: str | None) -> Path | None:
    """URL tĩnh (/uploads/...) → đường dẫn file thật trên đĩa."""
    if not url or not url.startswith("/uploads/"):
        return None
    p = Path(settings.upload_dir) / url[len("/uploads/"):]
    return p if p.is_file() else None


def build_exam_paper(*, exam_name: str, sitting_name: str, questions: list[dict],
                     with_answers: bool = False) -> bytes:
    """Đề thi bản giấy.

    ``with_answers=True`` in kèm đáp án đúng — bản dành cho hội đồng chấm, TUYỆT
    ĐỐI không phát cho thí sinh. Bên gọi phải tự bảo đảm điều đó (endpoint đánh
    dấu rõ trong tên file)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"{exam_name} — {sitting_name}")
    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Title"], fontName=_FONT_BOLD, fontSize=15)
    q_style = ParagraphStyle("q", parent=styles["BodyText"], fontName=_FONT,
                             fontSize=10.5, leading=14, alignment=TA_LEFT,
                             spaceBefore=6)
    o_style = ParagraphStyle("o", parent=q_style, leftIndent=14, spaceBefore=1)
    ok_style = ParagraphStyle("ok", parent=o_style, textColor=colors.HexColor("#166534"),
                              fontName=_FONT_BOLD)

    story: list = [Paragraph(_escape(f"{exam_name} — {sitting_name}"), h),
                   Spacer(1, 4 * mm)]
    if with_answers:
        story.append(Paragraph(
            "<b>BẢN CÓ ĐÁP ÁN — CHỈ DÀNH CHO HỘI ĐỒNG</b>",
            ParagraphStyle("w", parent=q_style, textColor=colors.red)))
        story.append(Spacer(1, 3 * mm))

    letters = ("A", "B", "C", "D")
    for i, q in enumerate(questions):
        story.append(Paragraph(f"<b>Câu {i + 1}.</b> {_escape(q.get('text') or '')}", q_style))
        for im in q.get("images") or []:
            p = _image_path(im.get("url"))
            if p is None:
                continue
            try:
                img = RLImage(str(p))
                scale = min(1.0, (MAX_IMG_W_MM * mm) / img.imageWidth)
                img.drawWidth = img.imageWidth * scale
                img.drawHeight = img.imageHeight * scale
                story.append(img)
            except Exception as exc:  # noqa: BLE001 — thiếu một ảnh không được làm hỏng cả đề
                logger.warning("Bỏ qua ảnh không đọc được (%s): %s", p, exc)
        correct = (q.get("correct_option") or "").upper()
        for letter, opt in zip(letters, q.get("options") or []):
            text = _escape(opt.get("text") or "") if isinstance(opt, dict) else _escape(str(opt))
            style = ok_style if (with_answers and letter == correct) else o_style
            mark = " ✔" if (with_answers and letter == correct) else ""
            story.append(Paragraph(f"{letter}. {text}{mark}", style))

    if not questions:
        story.append(Paragraph("Buổi thi này chưa có đề.", q_style))
    story.append(PageBreak())
    doc.build(story)
    return buf.getvalue()
