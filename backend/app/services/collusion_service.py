"""Chỉ số trùng khớp đáp án — dấu hiệu chép bài (đợt 4).

Phép đếm kinh điển của khảo thí: hai bài **cùng sai một kiểu** mới đáng ngờ. Cùng
chọn đúng là chuyện bình thường của người học được bài; nhưng cùng chọn SAI *cùng
một đáp án sai* ở nhiều câu thì xác suất ngẫu nhiên rất thấp.

Hai quyết định quan trọng:

1. **Chỉ so trong CÙNG PHÒNG.** Ngồi cạnh nhau mới chép được nhau. Ngoài ra đây còn
   là điều kiện để chạy nổi: 500 thí sinh so đôi một là 124.750 cặp; chia ~10 phòng
   thì mỗi phòng ~1.200 cặp, tổng ~12.000 — nhỏ hơn mười lần.
2. **Chỉ chạy sau khi buổi đã đóng.** Đây là việc hậu kiểm; quét giữa giờ vừa tốn
   vừa cho kết quả nửa vời (bài chưa làm xong).

Kết quả là DẤU HIỆU để hội đồng xem xét, không phải bằng chứng — đề trộn thứ tự nên
trùng ngẫu nhiên vẫn xảy ra, và hai người học cùng một tài liệu sai cũng sai giống
nhau. Giao diện phải nói rõ điều đó.
"""

from __future__ import annotations

import uuid
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Answer, Candidate, ExamSession, Room
from app.models.enums import FINALISED_STATUSES

# Dưới ngưỡng này thì không đáng gọi là dấu hiệu — vài câu trùng là chuyện thường
# gặp trong một phòng thi bình thường.
MIN_SHARED_WRONG = 3


async def find_suspicious_pairs(
    db: AsyncSession,
    sitting,
    answer_key: dict[str, dict],
    limit: int = 50,
) -> list[dict]:
    """Các cặp thí sinh cùng phòng có nhiều câu SAI GIỐNG HỆT nhau.

    ``answer_key`` = {question_id: {"correct_option": ...}} (lấy từ report_snapshot
    nên vẫn dùng được sau khi đề đã bị xoá).
    """
    correct = {qid: (v.get("correct_option") or "") for qid, v in answer_key.items()}

    rows = (await db.execute(
        select(ExamSession.id, Candidate.id, Candidate.cccd, Candidate.full_name,
               Candidate.room_id, Room.name)
        .join(Candidate, Candidate.id == ExamSession.candidate_id)
        .outerjoin(Room, Room.id == Candidate.room_id)
        .where(ExamSession.sitting_id == sitting.id,
               ExamSession.status.in_(FINALISED_STATUSES))
    )).all()
    if len(rows) < 2:
        return []

    info = {sid: {"candidate_id": cid, "cccd": cccd, "full_name": name,
                  "room_id": room_id, "room_name": room_name}
            for sid, cid, cccd, name, room_id, room_name in rows}

    # Chỉ nạp các đáp án SAI: đó là toàn bộ dữ liệu phép đếm cần, và với 500 bài ×
    # 280 câu thì bỏ phần đúng đi là nhẹ hẳn.
    wrong: dict[uuid.UUID, dict[str, str]] = {sid: {} for sid in info}
    ans = (await db.execute(
        select(Answer.session_id, Answer.question_id, Answer.selected_option)
        .where(Answer.session_id.in_(list(info)), Answer.selected_option.is_not(None))
    )).all()
    for sid, qid, opt in ans:
        if correct.get(str(qid)) != opt:
            wrong[sid][str(qid)] = opt

    # Gom theo phòng. Thí sinh chưa được xếp phòng (room_id None) gom thành một
    # nhóm riêng thay vì bỏ qua — kỳ thi nhỏ có thể không chia phòng.
    by_room: dict = {}
    for sid, meta in info.items():
        by_room.setdefault(meta["room_id"], []).append(sid)

    pairs: list[dict] = []
    for room_id, sids in by_room.items():
        for a, b in combinations(sids, 2):
            wa, wb = wrong[a], wrong[b]
            if not wa or not wb:
                continue
            # Duyệt bên nhỏ hơn cho rẻ.
            if len(wb) < len(wa):
                wa, wb = wb, wa
            shared = sum(1 for qid, opt in wa.items() if wb.get(qid) == opt)
            if shared < MIN_SHARED_WRONG:
                continue
            ia, ib = info[a], info[b]
            pairs.append({
                "a_candidate_id": str(ia["candidate_id"]), "a_cccd": ia["cccd"],
                "a_name": ia["full_name"],
                "b_candidate_id": str(ib["candidate_id"]), "b_cccd": ib["cccd"],
                "b_name": ib["full_name"],
                "room_name": ia["room_name"],
                "shared_wrong": shared,
                # Mẫu số: số câu SAI của người sai ít hơn. Tỉ lệ cao nghĩa là gần
                # như mọi câu sai của người đó đều trùng với người kia.
                "wrong_a": len(wrong[a]), "wrong_b": len(wrong[b]),
                "ratio": round(shared / max(1, min(len(wrong[a]), len(wrong[b]))), 3),
            })

    pairs.sort(key=lambda p: (-p["shared_wrong"], -p["ratio"]))
    return pairs[:limit]
