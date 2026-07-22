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
  paused: boolean;
  self_registered: boolean;
  room_id: string | null;
  room_name: string | null;
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
}

export interface RosterResponse {
  sitting: RosterSitting;
  assigned_total: number;
  logged_in: number;
  not_logged_in_total: number;
  self_registered_total: number;
  not_logged_in: RosterCandidate[];
  // Đồng hồ thi chung (AD-78): deadline sớm nhất trong các phiên đang làm + giờ server.
  earliest_end_time: string | null;
  server_time: string | null;
  running_count: number;
}

/** Session-level controls (chủ tịch on any owned exam; giám thị on their room). */
export const monitorApi = {
  pauseSession: async (sessionId: string) =>
    (await api.post(`/admin/sessions/${sessionId}/pause`)).data,
  resumeSession: async (sessionId: string) =>
    (await api.post(`/admin/sessions/${sessionId}/resume`)).data,
  logout: async (sessionId: string) =>
    (await api.post(`/admin/sessions/${sessionId}/logout`)).data,
  admit: async (sessionId: string) =>
    (await api.post(`/admin/sessions/${sessionId}/admit`)).data,
};
