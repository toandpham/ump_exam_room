import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { examApi, type QuestionsResponse } from "../api/exam";
import type { WsEvent } from "./useExamSocket";
import { useAntiCheat } from "./useAntiCheat";

export type SaveStatus = "saved" | "saving" | "disconnected";

/** Số giây cuối bài mà client đẩy đáp án dồn nhịp (thay vì 10s) để đáp án phút chót
 * kịp về server TRƯỚC end_time — xem chú thích ở effect flush bên dưới. */
const END_FLUSH_WINDOW_S = 20;

/** The single candidate WebSocket lives in ExamShell (App.tsx); this hook just
 * borrows it — `send` reports tab changes, `subscribe` delivers control events. */
export interface ExamWs {
  send: (obj: unknown) => void;
  subscribe: (handler: (e: WsEvent) => void) => () => void;
}

/** A 4xx means the server rejected the answer for good (e.g. "Đã hết giờ" after
 * end_time, or pause) — retrying is pointless and would pin "Mất kết nối"
 * forever. Only network/5xx errors are worth retrying. */
function isPermanentError(err: unknown): boolean {
  return (
    axios.isAxiosError(err) &&
    err.response != null &&
    err.response.status >= 400 &&
    err.response.status < 500
  );
}

/** Owns the live exam-session state: answers + autosave, the server-anchored
 * countdown, pause/time-up flags, WS end-exam handling, anti-cheat tab counting
 * and submit. Pure UI state (current question, calculator) stays in the screen.
 *
 * Per AD-47 the timer is per-candidate: when it hits 0 the client locks input and
 * the SERVER auto-submits + scores within ~5s; the fast /state poll then flips the
 * screen to the result. Pause is also per-candidate (state.paused). */
export function useExamSession(
  sessionId: string,
  data: QuestionsResponse | undefined,
  onSubmitted: () => void,
  ws: ExamWs,
) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [paused, setPaused] = useState(false);
  // Đáp án "bẩn" chờ đẩy lên server theo LÔ (AD-69) — gộp để giảm số request.
  const dirtyRef = useRef<Record<string, string | null>>({});
  const submittedRef = useRef(false);
  // Đếm số lần đồng bộ lô hỏng liên tiếp — chỉ báo "mất kết nối" sau vài lần (debounce).
  const failCountRef = useRef(0);

  const ansKey = `answers_${sessionId}`;

  // Borrow the shared socket (owned by ExamShell): end-exam control pushes
  // everyone to the result screen; tab changes are reported via `send`.
  const { send, subscribe } = ws;
  useEffect(() => subscribe((e) => {
    if (e.type === "exam_ended") doSubmit(true);
  }), [subscribe]);
  const onTabChange = useCallback((count: number) => send({ type: "tab_change", count }), [send]);
  const { tabCount } = useAntiCheat(onTabChange);

  // Time's up = locked client-side; the server sweep auto-submits this candidate
  // (AD-47). A proctor Cộng giờ moves end_time forward → the poll clears this.
  const timeUp = secondsLeft != null && secondsLeft <= 0 && !paused;

  // Initialise answers from server + localStorage.
  useEffect(() => {
    if (!data) return;
    const stored = JSON.parse(localStorage.getItem(ansKey) || "{}");
    setAnswers({ ...data.answers, ...stored });
    if (data.time_remaining_seconds != null) setSecondsLeft(data.time_remaining_seconds);
  }, [data]);

  // Local countdown — frozen while paused; stops at 0 without submitting.
  useEffect(() => {
    if (secondsLeft == null || paused) return;
    if (secondsLeft <= 0) return;   // hết giờ — dừng; server tự nộp (AD-47)
    const t = setTimeout(() => setSecondsLeft((s) => (s == null ? s : Math.max(0, s - 1))), 1000);
    return () => clearTimeout(t);
  }, [secondsLeft, paused]);

  // Resync timer with server: fast (5s) while paused OR time's up — so a proctor
  // resume / Cộng giờ / finalise is reflected promptly; 30s during normal play.
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const st = await examApi.state();
        setPaused(!!st.paused);
        if (st.time_remaining_seconds != null) setSecondsLeft(st.time_remaining_seconds);
        if (st.status === "submitted" || st.status === "timeout") onSubmitted();
      } catch { /* ignore */ }
    }, (paused || timeUp) ? 5000 : 30000);
    return () => clearInterval(id);
  }, [paused, timeUp]);

  // Đẩy đáp án theo LÔ (AD-69) thay vì POST mỗi lần chọn → giảm mạnh số request + WS
  // (chịu ~1000 máy). Đáp án luôn lưu localStorage ngay nên không mất khi reload.
  // Bình thường mỗi 10s; khi SẮP hết giờ (≤20s cuối) rút xuống ~2.5s + lệch ngẫu
  // nhiên theo máy: đáp án chọn phút chót KỊP về server TRƯỚC end_time (answersBulk
  // trả 409 sau end_time → flush sau khi hết giờ là vô ích), đồng thời rải 500 máy ra
  // thay vì dồn một gai request tại đúng T=0. flushBatch tự no-op khi không có đáp án
  // bẩn nên nhịp nhanh chỉ tốn mạng ở máy thực sự vừa đổi đáp án.
  const nearEnd =
    secondsLeft != null && secondsLeft > 0 && secondsLeft <= END_FLUSH_WINDOW_S && !paused;
  useEffect(() => {
    if (timeUp || paused) return;   // hết giờ: server từ chối; tạm dừng: khỏi đẩy (409)
    const base = nearEnd ? 2500 : 10000;
    const jitter = nearEnd ? Math.floor(Math.random() * 1500) : 0;   // rải, khỏi dồn 1 nhịp
    const id = setInterval(() => { void flushBatch(); }, base + jitter);
    return () => clearInterval(id);
  }, [nearEnd, timeUp, paused]);

  // AD-88: đẩy SỚM ~2.5s sau lần đổi đáp án (gộp các lần đổi liên tiếp trong cửa sổ).
  // Sự cố thực địa 16-07: máy trục trặc giữa giờ → đáp án chưa kịp theo nhịp 10s lên
  // server → qua máy khác mất bài. Debounce này thu cửa sổ mất còn ~3s. Tải server có
  // trần = 1 request/2.5s cho MỖI thí sinh đang đổi đáp án (500 máy đồng loạt ≈ 200
  // req/s = đúng mức load test AD-44 đã pass); thực tế thấp hơn nhiều vì mỗi câu làm
  // ~30s+. Nhịp 10s ở trên giữ làm lưới an toàn/retry.
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Gương ref của paused/timeUp cho callback hẹn giờ (closure sẽ ôm giá trị cũ):
  // nổ flush ĐÚNG LÚC vừa bị tạm dừng → server 409 → flushBatch tưởng "từ chối vĩnh
  // viễn" mà vứt đáp án khỏi hàng chờ → mất điểm câu đó. Gặp pause/hết giờ thì thôi,
  // để nhịp 10s đẩy lại sau khi được tiếp tục.
  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  const timeUpRef = useRef(timeUp);
  timeUpRef.current = timeUp;
  useEffect(() => () => {                       // dọn timer khi unmount
    if (debounceRef.current) clearTimeout(debounceRef.current);
  }, []);
  function scheduleFlushSoon() {
    if (debounceRef.current) return;            // đã hẹn — lần đổi sau gộp chung lô
    debounceRef.current = setTimeout(() => {
      debounceRef.current = null;
      if (pausedRef.current || timeUpRef.current) return;
      void flushBatch();
    }, 2500);
  }

  async function flushBatch() {
    const snapshot = { ...dirtyRef.current };
    const keys = Object.keys(snapshot);
    if (keys.length === 0) return;
    try {
      await examApi.answersBulk(keys.map((qid) => ({ question_id: qid, selected_option: snapshot[qid] })));
      failCountRef.current = 0;   // đồng bộ OK → reset đếm lỗi
      // Chỉ xoá khoá nào CHƯA bị đổi giữa chừng (đổi rồi → để lô sau đẩy).
      for (const qid of keys) if (dirtyRef.current[qid] === snapshot[qid]) delete dirtyRef.current[qid];
      if (Object.keys(dirtyRef.current).length === 0) setSaveStatus("saved");
    } catch (err) {
      // 4xx (hết giờ/tạm dừng) → bỏ (server từ chối vĩnh viễn); mạng/5xx → giữ, thử lại lô sau.
      if (isPermanentError(err)) { dirtyRef.current = {}; failCountRef.current = 0; setSaveStatus("saved"); return; }
      // Đáp án ĐÃ an toàn ở localStorage. Chỉ hiện "mất kết nối" sau vài lần đồng bộ
      // hỏng liên tiếp (debounce) — tránh nhấp nháy gây hoang mang lúc cao điểm.
      failCountRef.current += 1;
      if (failCountRef.current >= 2) setSaveStatus("disconnected");
    }
  }

  function selectOption(qid: string, opt: string) {
    if (timeUp || paused) return;   // hết giờ / tạm dừng → khoá, không cho đổi đáp án
    const next = { ...answers, [qid]: opt };
    setAnswers(next);
    localStorage.setItem(ansKey, JSON.stringify(next));   // lưu local ngay (bền vững)
    dirtyRef.current[qid] = opt;
    scheduleFlushSoon();                                   // AD-88: lên server sau ~2.5s
    setSaveStatus("saved");                                // đã an toàn ở máy con
  }

  // Thực hiện nộp bài (KHÔNG hỏi xác nhận ở đây — xác nhận do màn thi hiện hộp
  // thoại TRONG TRANG; tránh confirm() gốc của Windows vì trong chế độ kiosk nó là
  // cửa sổ riêng → dễ kẹt/cướp focus). `auto` giữ lại cho tương thích lời gọi.
  async function doSubmit(_auto: boolean) {
    if (submittedRef.current) return;
    submittedRef.current = true;
    await flushBatch();   // đẩy nốt đáp án còn lại TRƯỚC khi nộp (server chấm theo DB)
    try { await examApi.submit(); } catch { /* server may already have it */ }
    localStorage.removeItem(ansKey);
    onSubmitted();
  }

  return { answers, selectOption, saveStatus, secondsLeft, paused, timeUp, doSubmit, tabCount };
}
