import { api } from "./client";
import type { RosterSitting } from "./types";

export interface SessionSummary {
  session_id: string;
  candidate_id: string;
  cccd: string;
  full_name: string;
  unit: string;
  category: string;
  attempt_number: number;
  photo_path: string | null;
  status: string;
  submitted_at: string | null;
  /** Mốc hết giờ RIÊNG của thí sinh này (đồng hồ là per-candidate, AD-47). */
  end_time: string | null;
  paused: boolean;
  /** Số khiếu nại câu hỏi CHƯA xử lý của thí sinh này. */
  open_question_reports: number;
  /** Lý do bị đình chỉ thi (status = 'terminated'). */
  terminated_reason: string | null;
  /** Đang tạm dừng VÀ đã quá end_time — bài sẽ không bao giờ tự nộp (AD-121 #2). */
  overdue_paused: boolean;
  self_registered: boolean;
  room_id: string | null;
  room_name: string | null;
  // AD-110: máy đã tải xong toàn bộ ảnh đề (báo về từ máy thí sinh lúc chờ).
  preloaded: boolean;
  /** Thí sinh đã bấm "Báo giám thị" (sai thông tin), chưa được sửa. */
  info_disputed: boolean;
  /** Máy im lặng >90s = mất kết nối THẬT (chớp mạng ngắn không tính). */
  offline: boolean;
  last_seen_seconds: number | null;
}

export interface RosterCandidate {
  candidate_id: string;
  cccd: string;
  full_name: string;
  unit: string;
  category: string;
  attempt_number: number;
  photo_path: string | null;
  self_registered: boolean;
  room_name: string | null;
  info_disputed: boolean;
}

export interface RosterResponse {
  sitting: RosterSitting;
  assigned_total: number;
  logged_in: number;
  not_logged_in_total: number;
  not_logged_in: RosterCandidate[];
  // Đồng hồ thi chung (AD-78): deadline sớm nhất trong các phiên đang làm + giờ server.
  earliest_end_time: string | null;
  /** Mốc của người kết thúc muộn nhất (vào trễ / cộng giờ riêng). */
  latest_end_time: string | null;
  server_time: string | null;
}

/** Session-level controls (chủ tịch on any owned exam; giám thị on their room). */
export const monitorApi = {
  pauseSession: async (sessionId: string) =>
    (await api.post(`/admin/sessions/${sessionId}/pause`)).data,
  resumeSession: async (sessionId: string) =>
    (await api.post(`/admin/sessions/${sessionId}/resume`)).data,
  /** Thoát phần mềm thi trên đúng MÁY của một thí sinh (AD-128). */
  kioskQuitSession: async (sessionId: string): Promise<{ targeted: boolean; detail?: string }> =>
    (await api.post(`/admin/sessions/${sessionId}/kiosk-quit`)).data,
  logout: async (sessionId: string) =>
    (await api.post(`/admin/sessions/${sessionId}/logout`)).data,
  admit: async (sessionId: string) =>
    (await api.post(`/admin/sessions/${sessionId}/admit`)).data,
  /** Cộng giờ cho RIÊNG một thí sinh (máy treo/hỏng) — không đụng cả phòng. */
  extendSession: async (sessionId: string, minutes: number) =>
    (await api.post(`/admin/sessions/${sessionId}/extend`, { minutes })).data,
  /** Đình chỉ thi: dừng hẳn bài, chấm với những gì đã làm. Lý do bắt buộc. */
  terminateSession: async (sessionId: string, reason: string) =>
    (await api.post(`/admin/sessions/${sessionId}/terminate`, { reason })).data,
  /** Khiếu nại câu hỏi của thí sinh trong buổi này (chưa xử lý lên trước). */
  questionReports: async (sittingId: string): Promise<QuestionReport[]> =>
    (await api.get(`/admin/sittings/${sittingId}/question-reports`)).data,
  resolveQuestionReport: async (reportId: string, resolution: string) =>
    (await api.post(`/admin/question-reports/${reportId}/resolve`, { resolution })).data,
};

export interface QuestionReport {
  id: string;
  candidate_id: string;
  cccd: string;
  full_name: string;
  room_name: string | null;
  question_id: string;
  /** Số thứ tự câu TRONG ĐỀ CỦA THÍ SINH ĐÓ (đề trộn nên mỗi người một thứ tự). */
  question_number: number;
  content: string;
  created_at: string;
  resolved_at: string | null;
  resolution: string | null;
  resolved_by_name: string | null;
}
