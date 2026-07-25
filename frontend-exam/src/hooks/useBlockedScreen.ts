import axios from "axios";

/** Lý do server CHẶN truy cập, đọc từ lỗi của query hiện tại. Tách khỏi App.tsx ở
 * refactor đợt 3: LoginGate và ExamShell trước đây lặp y hệt khối này.
 *
 *  - `kiosk`   → 403 detail.code = kiosk_required: mở bằng trình duyệt thường (AD-91)
 *  - `license` → 403 code = license_* ở CẤP CAO NHẤT body (middleware giấy phép, AD-74)
 *  - `kicked`  → 409 detail.code = device_superseded: CCCD đăng nhập ở máy khác (AD-26)
 */
export type BlockedReason = "kiosk" | "license" | "kicked" | null;

export function useBlockedScreen(error: unknown): BlockedReason {
  if (!axios.isAxiosError(error)) return null;
  const res = error.response;
  if (!res) return null;
  const detailCode = (res.data as any)?.detail?.code;
  if (res.status === 409 && detailCode === "device_superseded") return "kicked";
  if (res.status !== 403) return null;
  if (detailCode === "kiosk_required") return "kiosk";
  if (String((res.data as any)?.code ?? "").startsWith("license_")) return "license";
  return null;
}
