import { useEffect, useRef, useState } from "react";
import { examApi, type QuestionsResponse } from "../api/exam";
import { imageUrlsOf, preloadAllFast, preloadAllPaced } from "../lib/preload";

/** Nạp trước ảnh đề + báo server khi máy đã tải đủ (AD-110). Tách khỏi App.tsx ở
 * refactor đợt 3 — giữ NGUYÊN semantics, chỉ gom 2 effect + state tiến độ:
 *
 *  - `ready` (đã phát đề, đồng hồ chưa chạy): tải NHANH toàn bộ ảnh về cache đĩa,
 *    trả tiến độ cho màn chờ hiện "Đang tải đề X/Y". Tải đủ (kể cả đề 0 ảnh → 0/0)
 *    → gọi `preload-done` ĐÚNG MỘT LẦN cho phiên đó; bảng giám sát đếm cờ này để
 *    khoá/mở nút "Bắt đầu thi" (lỗi mạng → thử lại sau 5s).
 *  - `in_progress`: chỉ còn luồng rải chậm (~1 ảnh/giây) vét phần sót cho máy vào
 *    trễ / rớt mạng lúc chờ. Sổ `seen` trong lib/preload chống tải trùng.
 *
 * Khoá theo `session_id`: buổi mới = phiên mới → báo lại từ đầu.
 */
export function usePreloadDeck(
  status: string | null | undefined,
  sessionId: string | null | undefined,
  questions: QuestionsResponse | undefined,
): { download: { done: number; total: number } | null } {
  const [download, setDownload] = useState<{ done: number; total: number } | null>(null);
  const reportedFor = useRef<string | null>(null);   // phiên đã báo "tải xong"

  useEffect(() => {
    if (status !== "ready" || !questions) return;
    const sid = sessionId;
    return preloadAllFast(imageUrlsOf(questions.questions), (done, total) => {
      setDownload({ done, total });
      if (done >= total && sid && reportedFor.current !== sid) {
        reportedFor.current = sid;
        examApi.preloadDone().catch(() => {
          reportedFor.current = null;   // lỗi mạng → thử lại ở tick tải kế / poll sau
          setTimeout(() => {
            void examApi.preloadDone()
              .then(() => { reportedFor.current = sid; })
              .catch(() => {});
          }, 5000);
        });
      }
    });
  }, [status, sessionId, questions]);

  useEffect(() => {
    if (status !== "in_progress" || !questions) return;
    return preloadAllPaced(imageUrlsOf(questions.questions));
  }, [status, questions]);

  return { download };
}
