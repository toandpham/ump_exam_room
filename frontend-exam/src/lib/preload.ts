/** Nạp trước ảnh đề một cách TIẾT CHẾ (AD-90).
 *
 * Máy thi thật gồm ~320 máy Win7/4GB RAM. Nạp ảnh của cả bộ đề (hàng trăm câu)
 * cùng lúc trên mọi máy vừa dồn mạng lúc phát đề, vừa giữ toàn bộ ảnh đã giải
 * nén trong RAM → máy yếu swap → "ì ạch". Ở đây chỉ nạp một cửa sổ nhỏ quanh câu
 * thí sinh đang làm, mỗi lần tối đa `CONCURRENCY` ảnh.
 */

/** Số câu ĐẦU đề được nạp ảnh sẵn trong lúc chờ bắt đầu. */
export const PREFETCH_QUESTIONS = 8;

/** Số câu KẾ TIẾP được nạp ảnh trước khi thí sinh tới. */
export const PRELOAD_AHEAD = 3;

const CONCURRENCY = 2;

/** URL đã yêu cầu nạp — khỏi tạo lại Image cho cùng một ảnh. */
const seen = new Set<string>();

/** Nạp lần lượt (tối đa CONCURRENCY ảnh song song). Không trả Promise: gọi xong
 * là quên, ảnh nằm sẵn trong cache HTTP của trình duyệt. */
export function preloadImages(urls: string[]): void {
  const queue = urls.filter((u) => u && !seen.has(u));
  queue.forEach((u) => seen.add(u));
  if (queue.length === 0) return;

  let i = 0;
  const next = () => {
    if (i >= queue.length) return;
    const img = new Image();
    img.onload = img.onerror = next;
    img.src = queue[i++];
  };
  for (let n = 0; n < CONCURRENCY; n++) next();
}
