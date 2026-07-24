/** AD-112: chế độ GIẢN LƯỢC cho máy yếu — tự cắt các hiệu ứng tốn công vẽ
 * (đổ bóng, transition khi rê chuột, animation, filter) trên máy ít RAM.
 * Bố cục + thông tin + nút bấm giữ nguyên 100%, chỉ bớt "đẹp".
 *
 * Tự bật khi trình duyệt báo máy ≤ 4GB RAM (`navigator.deviceMemory` — Chromium
 * làm tròn theo bậc 0.25/0.5/1/2/4/8 nên đội 320 máy Win7/4GB đều dính bậc ≤4;
 * 80 máy Win10/8GB báo 8 → giữ giao diện đầy đủ). Firefox không có API này →
 * không tự bật (dùng override khi cần).
 *
 * Override tay để thử/ép trên 1 máy (gõ trong DevTools hoặc đặt sẵn):
 *   localStorage.exam_lite = "1"  → ép BẬT   ·   "0" → ép TẮT
 */
export function shouldLite(deviceMemoryGb: number | undefined, override: string | null): boolean {
  if (override === "1") return true;
  if (override === "0") return false;
  return typeof deviceMemoryGb === "number" && deviceMemoryGb <= 4;
}

/** Gắn class `lite` vào <html> nếu máy thuộc diện giản lược (gọi 1 lần lúc boot). */
export function applyLiteMode(): boolean {
  let override: string | null = null;
  try {
    override = localStorage.getItem("exam_lite");
  } catch {
    /* ignore */
  }
  const mem = (navigator as { deviceMemory?: number }).deviceMemory;
  const lite = shouldLite(mem, override);
  if (lite) document.documentElement.classList.add("lite");
  return lite;
}
