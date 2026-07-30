/** Mô tả "mất kết nối bao lâu" cho giám sát.
 *
 * Ngưỡng báo động nằm ở BACKEND (device_lock.OFFLINE_ALERT_SECONDS = 90s) — cố ý
 * dài, vì chỉ báo cũ dùng 25 giây quá nhạy khiến cả bảng nhấp nháy mỗi lần máy Win7
 * khựng, và người vận hành đã yêu cầu gỡ bỏ. Ở đây chỉ lo hiển thị. */
export function offlineLabel(seconds: number | null | undefined): string {
  if (seconds == null) return "mất kết nối";
  if (seconds < 120) return `mất kết nối ${seconds}s`;
  return `mất kết nối ${Math.floor(seconds / 60)} phút`;
}
