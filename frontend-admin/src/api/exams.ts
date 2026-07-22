import { api } from "./client";
import type { Exam } from "./types";

export interface SittingDraft {
  name: string;
  scheduled_date?: string | null;
  duration_minutes?: number | null;
}

export interface SectionCreate {
  name: string;
  description?: string | null;
  duration_minutes: number;
  exam_date?: string | null;
  allow_registration?: boolean;
  // Initial structure declared in the create wizard (AD-47/48).
  room_count?: number;
  room_capacity?: number;   // max thí sinh mỗi phòng (0 = không giới hạn)
  sittings?: SittingDraft[];
}

export const examsApi = {
  list: async (): Promise<Exam[]> => (await api.get("/admin/exams")).data,
  get: async (id: string): Promise<Exam> => (await api.get(`/admin/exams/${id}`)).data,
  create: async (body: SectionCreate): Promise<Exam> =>
    (await api.post("/admin/exams", body)).data,
  remove: async (id: string): Promise<void> => { await api.delete(`/admin/exams/${id}`); },
  // Archive the exam (force-submit running buổi, close) so a new one can be created.
  close: async (id: string): Promise<{ submitted: number }> =>
    (await api.post(`/admin/exams/${id}/close`)).data,
  /** Gửi lệnh ĐÓNG phần mềm thi trên mọi máy (AD-93 — không còn khởi động lại máy).
   * Máy chủ từ chối (409) khi còn thí sinh đang làm bài; `force` để vẫn gửi. */
  kioskQuit: async (examId: string, force = false): Promise<{ ok: boolean; ttl: number }> =>
    (await api.post(`/admin/exams/${examId}/kiosk-quit`, null, { params: { force } })).data,
};

/** Trigger a browser download from a Blob. Used by report/candidate exports. */
export function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
