import { api } from "./client";

// Cập nhật hệ thống từ trang Quản trị (AD-89).
export interface UpdateStatus {
  state: "unknown" | "idle" | "running" | "done" | "failed";
  update_available: boolean;
  local: string | null;
  remote: string | null;
  checked_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  message: string | null;
  log_tail: string[];
  queued: boolean;
  watcher_alive: boolean;
}

export const systemApi = {
  updateStatus: async (): Promise<UpdateStatus> =>
    (await api.get("/admin/system/update-status")).data,
  requestUpdate: async (): Promise<{ detail: string }> =>
    (await api.post("/admin/system/update")).data,
};
