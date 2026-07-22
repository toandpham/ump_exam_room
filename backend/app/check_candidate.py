"""CLI: tra cứu MỌI phiên thi của một thí sinh (AD-90).

Dùng khi có tranh cãi kiểu "thí sinh nói đã nộp và thấy số câu đúng, nhưng bảng
giám sát báo còn đang làm bài". Lệnh này in ra sự thật trong CSDL: thí sinh có
mấy phiên, thuộc buổi nào, trạng thái gì, nộp lúc mấy giờ, bao nhiêu đáp án.

Chạy trên máy chủ:

    docker compose exec backend python -m app.check_candidate <CCCD hoặc hộ chiếu>
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models import Answer, Candidate, Exam, ExamSession, Sitting


def _local(dt) -> str:
    return dt.astimezone().strftime("%d/%m %H:%M:%S") if dt else "—"


async def _run(ident: str) -> int:
    async with AsyncSessionLocal() as db:
        cand = await db.scalar(select(Candidate).where(Candidate.cccd == ident.strip().upper()))
        if cand is None:
            print(f"[!] Không có thí sinh nào mang số giấy tờ '{ident}'.")
            return 1
        exam = await db.get(Exam, cand.exam_id) if cand.exam_id else None
        print(f"Thí sinh : {cand.full_name} ({cand.cccd})")
        print(f"Kỳ thi   : {exam.name if exam else '— chưa gán —'}")

        rows = (await db.execute(
            select(ExamSession, Sitting.name)
            .join(Sitting, Sitting.id == ExamSession.sitting_id)
            .where(ExamSession.candidate_id == cand.id)
            .order_by(ExamSession.created_at)
        )).all()
        if not rows:
            print("Phiên thi: KHÔNG có phiên nào (chưa đăng nhập/xác nhận buổi nào).")
            return 0

        print(f"Phiên thi: {len(rows)} phiên")
        for s, sitting_name in rows:
            answered = await db.scalar(
                select(func.count(Answer.id)).where(
                    Answer.session_id == s.id, Answer.selected_option.is_not(None))
            ) or 0
            print(
                f"  • Buổi '{sitting_name}' | trạng thái = {s.status}"
                f" | bắt đầu {_local(s.started_at)} | hết giờ {_local(s.end_time)}"
                f" | nộp {_local(s.submitted_at)}"
                f" | đã trả lời {answered} câu"
                f" | điểm {s.score if s.score is not None else '—'}"
                f" | tạm dừng: {'CÓ' if s.paused_at else 'không'}"
            )
        if len(rows) > 1:
            print("\n[Lưu ý] Thí sinh có phiên ở NHIỀU buổi: bảng giám sát chỉ hiện phiên")
            print("        của buổi đang xem — kiểm tra đúng buổi trước khi kết luận.")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Xem mọi phiên thi của một thí sinh.")
    parser.add_argument("identifier", help="CCCD (12 số) hoặc số hộ chiếu")
    raise SystemExit(asyncio.run(_run(parser.parse_args().identifier)))


if __name__ == "__main__":
    main()
