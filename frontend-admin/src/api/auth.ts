import { api } from "./client";
import type { Admin } from "../stores/auth";

/** Admin authentication endpoints (password-only — AD-28). */
export const authApi = {
  login: async (username: string, password: string): Promise<{ access_token: string }> =>
    (await api.post("/admin/auth/login", { username, password })).data,
  logout: async (): Promise<void> => {
    await api.post("/admin/auth/logout");
  },
  me: async (): Promise<Admin> => (await api.get<Admin>("/admin/auth/me")).data,
};
