import { api } from "./client";
import { triggerDownload } from "./exams";
import type { Candidate, Paginated } from "./types";

export interface CandidateInput {
  cccd: string;
  full_name: string;
  birth_date: string;
  unit: string;
  graduation_year?: number | null;
  major?: string | null;
  category: string;
  attempt_number?: number;
  exam_id?: string | null;
}

export interface CandidateFilters {
  cccd?: string;
  full_name?: string;
  unit?: string;
  category?: string;
  has_photo?: boolean;
  exam_id?: string;
  page?: number;
  page_size?: number;
}

export interface ImportPreviewRow {
  row_number: number;
  data: Record<string, unknown>;
  errors: string[];
  valid: boolean;
}
export interface ImportPreview {
  token: string;
  total_rows: number;
  valid_count: number;
  error_count: number;
  rows: ImportPreviewRow[];
  expires_in: number;
}
export interface ZipReport {
  updated: number;
  matched: string[];
  unmatched_files: string[];
  invalid_files: string[];
}
export interface CandidateStats {
  total: number;
  with_photo: number;
  without_photo: number;
  assigned: number;
  unassigned: number;
  by_unit: Record<string, number>;
  by_category: Record<string, number>;
}
export interface SecurityEvent {
  id: string;
  event_type: string;
  cccd_attempted: string | null;
  client_ip: string | null;
  created_at: string;
  metadata: Record<string, unknown> | null;
}

function multipart(file: File): FormData {
  const fd = new FormData();
  fd.append("file", file);
  return fd;
}

export const candidatesApi = {
  list: async (f: CandidateFilters): Promise<Paginated<Candidate>> => {
    const params: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(f)) if (v !== undefined && v !== "") params[k] = v;
    return (await api.get("/admin/candidates", { params })).data;
  },
  create: async (body: CandidateInput): Promise<Candidate> =>
    (await api.post("/admin/candidates", body)).data,
  update: async (id: string, body: Partial<CandidateInput>): Promise<Candidate> =>
    (await api.patch(`/admin/candidates/${id}`, body)).data,
  remove: async (id: string): Promise<void> => { await api.delete(`/admin/candidates/${id}`); },
  uploadPhoto: async (id: string, file: File): Promise<Candidate> =>
    (await api.post(`/admin/candidates/${id}/photo`, multipart(file))).data,

  downloadTemplate: async () => {
    const res = await api.get("/admin/candidates/template.xlsx", { responseType: "blob" });
    triggerDownload(res.data, "candidate_template.xlsx");
  },
  importPreview: async (file: File): Promise<ImportPreview> =>
    (await api.post("/admin/candidates/import/preview", multipart(file))).data,
  importCommit: async (token: string, exam_id?: string | null) =>
    (await api.post("/admin/candidates/import/commit", { token, exam_id: exam_id || null })).data,
  uploadZip: async (file: File): Promise<ZipReport> =>
    (await api.post("/admin/candidates/photos/zip", multipart(file))).data,
  assignExam: async (exam_id: string, candidate_ids?: string[]) =>
    (await api.post("/admin/candidates/assign-exam", { exam_id, candidate_ids: candidate_ids ?? null })).data,
  stats: async (): Promise<CandidateStats> => (await api.get("/admin/candidates/stats")).data,
  exportXlsx: async (f: CandidateFilters) => {
    const params: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(f)) if (v !== undefined && v !== "" && k !== "page" && k !== "page_size") params[k] = v;
    const res = await api.get("/admin/candidates/export.xlsx", { params, responseType: "blob" });
    triggerDownload(res.data, "candidates.xlsx");
  },
  emergencyAdd: async (body: CandidateInput & { reason: string }): Promise<Candidate> =>
    (await api.post("/admin/candidates/emergency-add", body)).data,

  failedLogins: async (limit = 100): Promise<SecurityEvent[]> =>
    (await api.get("/admin/security/failed-logins", { params: { limit } })).data,
};
