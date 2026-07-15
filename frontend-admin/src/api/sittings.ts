import { api } from "./client";
import { triggerDownload } from "./exams";
import type { Sitting } from "./types";
import type { RosterResponse, SessionSummary } from "./monitor";
import type { ReportData } from "./reports";

export interface SittingCreate {
  name: string;
  description?: string | null;
  scheduled_date?: string | null;
  duration_minutes: number;
}
export interface SittingUpdate {
  name?: string;
  description?: string | null;
  scheduled_date?: string | null;
  duration_minutes?: number;
}

export interface IntegrityResult {
  checked: number;
  ok: number;
  mismatched: string[];
  unsealed_legacy: string[];
}

export const sittingsApi = {
  list: async (examId: string): Promise<Sitting[]> =>
    (await api.get(`/admin/exams/${examId}/sittings`)).data,
  get: async (id: string): Promise<Sitting> =>
    (await api.get(`/admin/sittings/${id}`)).data,
  create: async (examId: string, body: SittingCreate): Promise<Sitting> =>
    (await api.post(`/admin/exams/${examId}/sittings`, body)).data,
  update: async (id: string, body: SittingUpdate): Promise<Sitting> =>
    (await api.patch(`/admin/sittings/${id}`, body)).data,
  remove: async (id: string): Promise<void> => { await api.delete(`/admin/sittings/${id}`); },

  // The ONLY đề-load path: upload gói QTI đã mã hoá (.qenc, tool "Mã hoá đề thi")
  // kèm mã kích hoạt 8 số (đổi mỗi 30 phút — spec 2026-07-13).
  importQti: async (
    id: string, file: File, password: string,
    onProgress?: (pct: number) => void,
  ): Promise<Sitting> => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("password", password);
    return (await api.post(`/admin/sittings/${id}/import-qti`, fd, {
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total));
      },
    })).data;
  },

  open: async (id: string): Promise<Sitting> =>
    (await api.post(`/admin/sittings/${id}/open`)).data,

  // Run-control for a chosen buổi.
  distribute: async (id: string) => (await api.post(`/admin/sittings/${id}/distribute`)).data,
  start: async (id: string) => (await api.post(`/admin/sittings/${id}/start`)).data,
  pauseAll: async (id: string) => (await api.post(`/admin/sittings/${id}/pause-all`)).data,
  resumeAll: async (id: string) => (await api.post(`/admin/sittings/${id}/resume-all`)).data,
  end: async (id: string) => (await api.post(`/admin/sittings/${id}/end`)).data,
  integrity: async (id: string): Promise<IntegrityResult> =>
    (await api.get(`/admin/sittings/${id}/integrity`)).data,
  sessions: async (id: string): Promise<SessionSummary[]> =>
    (await api.get(`/admin/sittings/${id}/sessions`)).data,
  roster: async (id: string): Promise<RosterResponse> =>
    (await api.get(`/admin/sittings/${id}/roster`)).data,

  // Reports (per buổi).
  report: async (id: string): Promise<ReportData> =>
    (await api.get(`/admin/sittings/${id}/report`)).data,
  reportXlsx: async (id: string, password?: string) => {
    const res = await api.get(`/admin/sittings/${id}/report.xlsx`, {
      params: password ? { password } : undefined,
      responseType: "blob",
    });
    const cd = res.headers["content-disposition"] || "";
    const m = /filename="([^"]+)"/.exec(cd);
    const filename = m?.[1] || (password ? `report_${id}.zip` : `report_${id}.xlsx`);
    triggerDownload(res.data, filename);
  },
};
