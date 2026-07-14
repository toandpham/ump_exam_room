import axios from "axios";
import { useStore } from "../store";

// Stable per-browser id so the proctor can spot two candidates at one machine.
// crypto.randomUUID needs a secure context (HTTPS/localhost); the exam runs on
// plain-HTTP LAN, so fall back to getRandomValues, then Math.random.
function getDeviceId(): string {
  const KEY = "exam_device_id";
  let id = localStorage.getItem(KEY);
  if (!id) {
    if (crypto?.randomUUID) {
      id = crypto.randomUUID();
    } else if (crypto?.getRandomValues) {
      const b = crypto.getRandomValues(new Uint8Array(16));
      id = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
    } else {
      id = `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
    }
    localStorage.setItem(KEY, id);
  }
  return id;
}

const DEVICE_ID = getDeviceId();

export const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const token = useStore.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  config.headers["X-Device-Id"] = DEVICE_ID;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    // Only force logout on auth failure for non-login requests.
    if (error.response?.status === 401 && !error.config?.url?.includes("/auth/login")) {
      useStore.getState().logout();
    }
    return Promise.reject(error);
  },
);

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
