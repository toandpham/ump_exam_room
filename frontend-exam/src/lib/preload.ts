/** Nạp trước ảnh đề một cách TIẾT CHẾ (AD-90 / AD-90c).
 *
 * Máy thi thật gồm ~320 máy Win7/4GB RAM. Có 2 nhu cầu ngược nhau:
 *  - vào câu nào là ảnh phải hiện ngay (không chờ mạng);
 *  - KHÔNG được giữ cả bộ ảnh trong RAM (bản cũ làm vậy → máy 4GB swap → ì ạch).
 *
 * Cách giải: chỉ TẢI ảnh (không giữ tham chiếu) — bytes ảnh nằm lại trong CACHE ĐĨA
 * của trình duyệt (ảnh đề có tên = SHA-256 nội dung + Cache-Control immutable nên
 * đọc lại từ đĩa, không hỏi server). RAM chỉ giữ ảnh của câu đang hiển thị.
 *
 * Ba luồng nạp, dùng chung sổ ``seen`` nên không tải trùng:
 *  1. ``preloadAllFast`` — TOÀN BỘ đề, tải nhanh lúc CHỜ bắt đầu (AD-110) + báo
 *     tiến độ (màn chờ hiện "Đang tải đề X/Y", đủ thì báo server mở nút Bắt đầu).
 *  2. ``preloadAllPaced`` — TOÀN BỘ đề, rải chậm TRONG giờ thi (vét máy vào trễ):
 *     mỗi máy lệch giờ xuất phát + giãn nhịp từng ảnh, 400 máy không dồn mạng.
 *  3. ``preloadImages`` cho vài câu KẾ TIẾP (ExamScreen) — chen lên trước hàng đợi
 *     rải chậm khi thí sinh sắp tới câu đó.
 */

/** Số câu KẾ TIẾP được nạp ảnh trước khi thí sinh tới. (AD-106: 3→6 — hiện trường
 * báo "hình lúc nhanh lúc chậm" = thí sinh đi nhanh hơn luồng nạp; ảnh đã thu nhỏ
 * ~80KB nên nạp trước 6 câu vẫn nhẹ mạng.) */
export const PRELOAD_AHEAD = 6;

/** Số ảnh tải song song ở luồng "tải ngay". */
const CONCURRENCY = 2;

/** Rải 400 máy ra: mỗi máy chờ ngẫu nhiên tới ngần này trước khi bắt đầu nạp cả đề. */
export const START_STAGGER_MS = 5000;

/** Giãn cách giữa 2 ảnh ở luồng nạp cả đề (≈1 ảnh/giây, lệch nhịp mỗi máy). */
export const PACE_MIN_MS = 600;
export const PACE_JITTER_MS = 900;

/** URL đã bắt đầu tải — đánh dấu LÚC TẢI (không phải lúc xếp hàng) để luồng
 * "câu kế tiếp" vẫn chen lên trước được nếu hàng đợi rải chậm chưa tới. */
const seen = new Set<string>();

/** Chạy một hàng đợi tải ảnh. ``pace()`` trả số ms nghỉ giữa 2 ảnh (0 = liên tục).
 * Trả về hàm HUỶ (dừng ngay, dọn hẹn giờ). */
function startQueue(
  urls: string[],
  pace: () => number,
  concurrency: number,
  onLoaded?: () => void,
  onSkipped?: () => void,
): () => void {
  const queue = [...new Set(urls.filter(Boolean))];
  const timers = new Set<ReturnType<typeof setTimeout>>();
  let cancelled = false;
  let i = 0;

  const next = () => {
    if (cancelled) return;
    let url: string | undefined;
    while (i < queue.length) {
      const u = queue[i++];
      if (!seen.has(u)) { url = u; break; }     // ảnh đã tải ở luồng khác → bỏ qua
      // Fix kẹt "34/37" (AD-110b): ảnh bị luồng khác nẫng vẫn phải ĐƯỢC ĐẾM vào
      // tiến độ — không thì done không bao giờ chạm total → không báo preload-done
      // → nút Bắt đầu thi bên chủ tịch kẹt vĩnh viễn.
      onSkipped?.();
    }
    if (url === undefined) return;              // hết hàng đợi
    seen.add(url);
    const img = new Image();
    img.onload = img.onerror = () => {
      if (cancelled) return;
      onLoaded?.();
      const wait = pace();
      if (wait <= 0) { next(); return; }
      const t = setTimeout(() => { timers.delete(t); next(); }, wait);
      timers.add(t);
    };
    img.src = url;                              // không giữ tham chiếu: bytes vào cache đĩa
  };

  for (let n = 0; n < concurrency; n++) next();
  return () => {
    cancelled = true;
    timers.forEach(clearTimeout);
    timers.clear();
  };
}

/** Tải ngay một nhúm ảnh (vài câu quanh chỗ thí sinh đang đứng). */
export function preloadImages(urls: string[]): void {
  startQueue(urls, () => 0, CONCURRENCY);
}

/** AD-110: nạp TOÀN BỘ ảnh đề NHANH trong lúc CHỜ bắt đầu (đã phát đề, đồng hồ
 * chưa chạy) — dồn hết việc tải vào giai đoạn máy đang rảnh, để lúc thi không còn
 * tải nền làm ì máy yếu ("khúc đầu chậm, một hồi mới mượt"). Nghỉ rất ngắn giữa 2
 * ảnh (jitter) để 400 máy không khoá nhịp với nhau. Báo tiến độ qua ``onProgress``
 * (done/total, tính cả ảnh đã nằm sẵn trong cache) → màn chờ hiện "Đã tải X/Y".
 * Trả về hàm huỷ. */
export function preloadAllFast(
  urls: string[],
  onProgress?: (done: number, total: number) => void,
): () => void {
  const unique = [...new Set(urls.filter(Boolean))];
  const total = unique.length;
  // Đếm qua CHÍNH hàng đợi: mỗi URL được ghé đúng 1 lần — hoặc tự tải (onLoaded)
  // hoặc đã có luồng khác lo (onSkipped). Không đếm trước theo `seen` nữa (bản cũ
  // vừa đếm trước vừa bỏ-qua-không-đếm ảnh bị nẫng SAU snapshot → kẹt 34/37).
  let done = 0;
  onProgress?.(0, total);
  const bump = () => onProgress?.(++done, total);
  return startQueue(unique, () => 50 + Math.random() * 150, 2, bump, bump);
}

/** Nạp TOÀN BỘ ảnh đề xuống cache đĩa, rải chậm. Trả về hàm huỷ. */
export function preloadAllPaced(urls: string[]): () => void {
  let cancelQueue: (() => void) | null = null;
  let cancelled = false;
  const start = setTimeout(() => {
    if (cancelled) return;
    cancelQueue = startQueue(urls, () => PACE_MIN_MS + Math.random() * PACE_JITTER_MS, 1);
  }, Math.random() * START_STAGGER_MS);

  return () => {
    cancelled = true;
    clearTimeout(start);
    cancelQueue?.();
  };
}

/** Gom mọi URL ảnh (câu + đáp án) của một danh sách câu hỏi. AD-107: ưu tiên bản
 * NHỎ (thumbs — thứ thực sự hiển thị trong bài); bản đầy đủ chỉ tải khi phóng to. */
export function imageUrlsOf(
  questions: {
    images: string[]; thumbs?: string[];
    options: { images: string[]; thumbs?: string[] }[];
  }[],
): string[] {
  const urls: string[] = [];
  for (const q of questions) {
    q.images.forEach((src, i) => urls.push(q.thumbs?.[i] || src));
    for (const o of q.options) o.images.forEach((src, i) => urls.push(o.thumbs?.[i] || src));
  }
  return urls;
}
