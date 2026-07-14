import { api } from "./client";

// Giấy phép server (AD-74).
export interface LicenseInfo {
  status: "valid" | "trial" | "expired" | "missing" | "clock_tampered";
  issued_to: string | null;
  expires_at: string | null;
  days_left: number | null;
  warn: boolean;
}

export const licenseApi = {
  get: async (): Promise<LicenseInfo> => (await api.get("/admin/license")).data,
  set: async (key: string): Promise<LicenseInfo> =>
    (await api.post("/admin/license", { key })).data,
};
