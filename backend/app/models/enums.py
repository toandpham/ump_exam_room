"""Domain enumerations stored as strings in the database."""

from __future__ import annotations

from enum import Enum


class ExamStatus(str, Enum):
    # Exam (kỳ thi) is now a container (AD-47). ``active`` = open/live (accepting
    # sittings & registrations), ``closed`` = archived. ``draft`` kept for legacy.
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"


class SittingStatus(str, Enum):
    # Per-sitting (buổi thi) lifecycle (AD-47). A sitting carries its own đề and
    # run-control: ``draft`` (created, maybe no đề) → ``active`` (đề loaded,
    # accepting logins / running) → ``closed`` (ended + payload purged). At most
    # one sitting per exam may be ``active`` at a time.
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"


class SessionStatus(str, Enum):
    WAITING = "waiting"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    TIMEOUT = "timeout"
    # Chủ tịch đình chỉ thi giữa chừng (bắt gian lận, vi phạm quy chế). Bài ĐƯỢC
    # CHẤM với những gì đã làm và niêm phong như mọi bài khác — trạng thái riêng chỉ
    # để hội đồng phân biệt được trong báo cáo và nhật ký, lý do lưu ở
    # ``exam_sessions.terminated_reason``.
    TERMINATED = "terminated"
    # (Trạng thái "absent" đã gỡ — refactor đợt 3. Vắng nay tính ở BÁO CÁO cho thí
    # sinh KHÔNG có phiên; report_service dùng literal "absent" tổng hợp, không cần
    # enum. DB dev cũ có thể còn vài dòng status='absent' — cột là String, vô hại.)


# Bài đã chốt: không còn làm được nữa, đã có điểm + niêm phong. Định nghĩa MỘT chỗ
# vì mọi nơi hỏi "đã xong chưa" phải trả lời giống nhau — trước đây tập này được
# viết tay lặp lại ở 5 file, nên thêm một trạng thái là chắc chắn sót chỗ (thí sinh
# bị đình chỉ sẽ không xem được kết quả, hoặc biến mất khỏi báo cáo).
FINALISED_STATUSES = frozenset({
    SessionStatus.SUBMITTED.value,
    SessionStatus.TIMEOUT.value,
    SessionStatus.TERMINATED.value,
})


class AdminRole(str, Enum):
    SUPER_ADMIN = "super_admin"       # "Quản trị" — accounts, audit, view/delete exams
    PROCTOR = "proctor"               # "Chủ tịch hội đồng thi" (AD-47) — full exam orchestration
    ROOM_PROCTOR = "room_proctor"     # "Giám thị" (AD-47) — view own room + pause one candidate


class EventType(str, Enum):
    # Login / whitelist enforcement
    LOGIN_ATTEMPT_INVALID_CCCD = "login_attempt_invalid_cccd"
    LOGIN_ATTEMPT_NOT_IN_WHITELIST = "login_attempt_not_in_whitelist"
    LOGIN_ATTEMPT_NOT_IN_EXAM = "login_attempt_not_in_exam"
    LOGIN_RATE_LIMITED = "login_rate_limited"
    LOGIN_SUCCESS = "login_success"
    SAME_MACHINE_LOGIN = "same_machine_login"   # 2+ candidates active from one IP
    REGISTER_DUPLICATE_CCCD = "register_duplicate_cccd"
    REGISTER_SUCCESS = "register_success"
    # Session lifecycle / audit trail
    INFO_CONFIRM = "info_confirm"
    INFO_DISPUTE = "info_dispute"
    START = "start"
    SITTING_OPENED = "sitting_opened"       # buổi thi mở (draft→active), payload nạp Redis (AD-47)
    PAUSE = "pause"                         # per-candidate pause (AD-47)
    RESUME = "resume"                       # per-candidate resume (AD-47)
    TIMEOUT_SUBMIT = "timeout_submit"       # auto-submit when a candidate's own clock hits 0 (AD-47)
    TERMINATED = "terminated"               # chủ tịch đình chỉ thi 1 thí sinh (có lý do)
    TAB_CHANGE = "tab_change"
    SUBMIT = "submit"
    EMERGENCY_ADD = "emergency_add"
    PROCTOR_LOGOUT = "proctor_logout"       # giám thị/chủ tịch đăng xuất 1 thí sinh (AD-55 M4)
    EXAM_END = "exam_end"
    EXAM_PURGED = "exam_purged"             # encrypted_payload + Redis wiped after end
    RESULT_TAMPERED = "result_tampered"     # integrity check found hash mismatch
    RESULT_SEALED = "result_sealed"         # results_hash computed/stored after scoring
