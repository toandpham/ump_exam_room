import { api } from "./client";

export interface AdminAccount {
  id: string;
  username: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
}

export interface AdminCreate {
  username: string;
  password: string;
  full_name?: string | null;
  role: string;
}

export interface AdminSummary {
  id: string;
  username: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
}

export interface DashboardStats {
  exams: { total: number; active: number; closed: number };
  accounts: { total: number; super_admin: number; proctor: number; room_proctor: number };
  candidates_total: number;
  sessions_in_progress: number;
}

export type MetricStatus = "ok" | "warn" | "danger";

export interface ServerStats {
  system: {
    cpu: { percent: number; cores: number; load_avg: number[]; status: MetricStatus };
    memory: { total: number; used: number; percent: number; status: MetricStatus };
    disk: { total: number; used: number; percent: number; status: MetricStatus };
    network: { sent_per_sec: number; recv_per_sec: number; bytes_sent: number; bytes_recv: number };
    uptime_seconds: number;
  };
  database: {
    ok: boolean;
    connections_used?: number;
    connections_max?: number;
    connections_percent?: number;
    size_bytes?: number;
    status?: MetricStatus;
  };
  redis: { ok: boolean; used_memory?: number; connected_clients?: number };
}

export interface AuditEvent {
  id: string;
  event_type: string;
  cccd_attempted: string | null;
  client_ip: string | null;
  created_at: string;
  metadata: Record<string, unknown> | null;
}

export const adminsApi = {
  changeMyPassword: async (oldPassword: string, newPassword: string): Promise<void> => {
    await api.post("/admin/auth/change-password", { old_password: oldPassword, new_password: newPassword });
  },
  audit: async (params: { event_type?: string; q?: string; limit?: number }): Promise<AuditEvent[]> =>
    (await api.get("/admin/admins/audit", { params })).data,
  dashboard: async (): Promise<DashboardStats> => (await api.get("/admin/admins/dashboard")).data,
  serverStats: async (): Promise<ServerStats> => (await api.get("/admin/admins/server-stats")).data,
  list: async (): Promise<AdminAccount[]> => (await api.get("/admin/admins")).data,
  create: async (body: AdminCreate): Promise<AdminAccount> =>
    (await api.post("/admin/admins", body)).data,
  setPassword: async (id: string, password: string): Promise<AdminAccount> =>
    (await api.post(`/admin/admins/${id}/set-password`, { password })).data,

  // Room-proctor (giám thị) accounts — managed by the chủ tịch (proctor).
  roomProctors: async (): Promise<AdminSummary[]> =>
    (await api.get("/admin/admins/room-proctors")).data,
  createRoomProctor: async (body: { username: string; password: string; full_name?: string | null }): Promise<AdminSummary> =>
    (await api.post("/admin/admins/room-proctors", body)).data,
  setRoomProctorPassword: async (id: string, password: string): Promise<AdminSummary> =>
    (await api.post(`/admin/admins/room-proctors/${id}/set-password`, { password })).data,
  // Auto-reset a giám thị's password to a 6-digit PIN and read it back (AD-48).
  resetRoomProctorPin: async (id: string): Promise<{ id: string; username: string; full_name: string | null; pin: string }> =>
    (await api.post(`/admin/admins/room-proctors/${id}/reset-pin`)).data,
};
