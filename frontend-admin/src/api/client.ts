import axios from "axios";
import { useAuthStore } from "../stores/auth";

export const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().clear();
      if (!window.location.pathname.endsWith("/login")) {
        window.location.assign("/admin/login");
      }
    }
    // Giấy phép hết hạn/thiếu (AD-74): backend chặn mọi API bằng 403 license_* —
    // đưa thẳng về trang Giấy phép (super nhập key mới; vai trò khác thấy hướng dẫn).
    const code = error.response?.data?.code;
    if (
      error.response?.status === 403 &&
      typeof code === "string" &&
      code.startsWith("license_") &&
      !window.location.pathname.endsWith("/license")
    ) {
      window.location.assign("/admin/license");
    }
    return Promise.reject(error);
  },
);

/** Extract a human-friendly error message from an axios error. */
export function errorMessage(error: unknown, fallback = "Đã có lỗi xảy ra"): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
    if (detail?.message) return detail.message;
    // No usable detail — surface the HTTP status (or network) so a stale bundle
    // hitting a removed endpoint shows e.g. "(404)" instead of an opaque message.
    const status = error.response?.status;
    return status ? `${fallback} (HTTP ${status})` : `${fallback} (mất kết nối máy chủ)`;
  }
  return fallback;
}
