import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

// Mock the network + socket + anti-cheat deps so the hook runs in isolation.
const answer = vi.fn().mockResolvedValue({});
const answersBulk = vi.fn().mockResolvedValue({ saved: 1 });
const submit = vi.fn().mockResolvedValue({});
const state = vi.fn().mockResolvedValue({ paused: false, time_remaining_seconds: 60, status: "in_progress" });
vi.mock("../api/exam", () => ({ examApi: {
  answer: (...a: any[]) => answer(...a),
  answersBulk: (...a: any[]) => answersBulk(...a),
  submit: (...a: any[]) => submit(...a),
  state: (...a: any[]) => state(...a),
} }));
vi.mock("./useAntiCheat", () => ({ useAntiCheat: () => ({ tabCount: 0 }) }));

import { useExamSession, type ExamWs } from "./useExamSession";
import type { QuestionsResponse } from "../api/exam";

// The shared socket is owned by ExamShell; the hook just borrows send/subscribe.
const ws: ExamWs = { send: vi.fn(), subscribe: vi.fn(() => () => {}) };

const data = (timeLeft: number): QuestionsResponse => ({
  status: "in_progress",
  time_remaining_seconds: timeLeft,
  total: 1,
  answers: {},
  questions: [{ id: "q1", text: "Q", images: [], options: [{ id: "A", text: "a", images: [] }] }],
});

beforeEach(() => {
  localStorage.clear();
  answer.mockClear(); answersBulk.mockClear(); submit.mockClear(); state.mockClear();
  answersBulk.mockResolvedValue({ saved: 1 });
  state.mockResolvedValue({ paused: false, time_remaining_seconds: 60, status: "in_progress" });
});

describe("useExamSession (AD-69 batch save)", () => {
  it("persists locally immediately and does NOT POST per selection (batched)", () => {
    const d = data(60);
    const { result } = renderHook(() => useExamSession("s1", d, () => {}, ws));
    act(() => result.current.selectOption("q1", "A"));
    expect(result.current.answers).toEqual({ q1: "A" });
    expect(JSON.parse(localStorage.getItem("answers_s1")!)).toEqual({ q1: "A" });
    expect(result.current.saveStatus).toBe("saved");   // an toàn ở máy con ngay
    expect(answersBulk).not.toHaveBeenCalled();          // chưa đẩy (chờ lô)
  });

  it("flushes dirty answers as ONE bulk request on submit, then submits once", async () => {
    const onSubmitted = vi.fn();
    const d = data(60);
    const { result } = renderHook(() => useExamSession("s1", d, onSubmitted, ws));
    act(() => result.current.selectOption("q1", "A"));
    await act(async () => { await result.current.doSubmit(true); });
    expect(answersBulk).toHaveBeenCalledWith([{ question_id: "q1", selected_option: "A" }]);
    expect(submit).toHaveBeenCalledOnce();
    expect(onSubmitted).toHaveBeenCalledOnce();
    expect(localStorage.getItem("answers_s1")).toBeNull();
    await act(async () => { await result.current.doSubmit(true); });  // idempotent
    expect(submit).toHaveBeenCalledOnce();
  });

  it("bỏ hàng chờ khi phiên KHÔNG CÒN ở server (404) — khỏi kẹt 'Mất kết nối'", async () => {
    // Chỉ 401/403/404 mới là "server sẽ không bao giờ nhận" → bỏ hàng chờ là đúng.
    // 409 thì KHÔNG (xem test R3 bên dưới) — đó là trạng thái tạm thời.
    answersBulk.mockRejectedValueOnce({ isAxiosError: true, response: { status: 404 } });
    const d = data(60);
    const { result } = renderHook(() => useExamSession("s1", d, () => {}, ws));
    act(() => result.current.selectOption("q1", "A"));
    await act(async () => { await result.current.doSubmit(true); });
    expect(result.current.saveStatus).toBe("saved");
  });

  it("does NOT flash 'disconnected' on a single sync blip (debounced; data safe locally)", async () => {
    answersBulk.mockRejectedValueOnce({ isAxiosError: true, response: undefined });
    const d = data(60);
    const { result } = renderHook(() => useExamSession("s1", d, () => {}, ws));
    act(() => result.current.selectOption("q1", "A"));
    await act(async () => { await result.current.doSubmit(true); });   // 1 lần hỏng mạng
    expect(result.current.saveStatus).toBe("saved");                    // chưa báo (debounce)
  });

  it("shows 'disconnected' only after repeated sync failures", async () => {
    vi.useFakeTimers();
    try {
      answersBulk.mockRejectedValue({ isAxiosError: true, response: undefined });
      const d = data(120);
      const { result } = renderHook(() => useExamSession("s1", d, () => {}, ws));
      act(() => result.current.selectOption("q1", "A"));
      // Hai chu kỳ đẩy lô (10s) đều hỏng mạng → mới hiện "mất kết nối".
      await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
      await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
      expect(result.current.saveStatus).toBe("disconnected");
    } finally {
      vi.useRealTimers();
    }
  });

  it("AD-88: đáp án lên server ~2.5s sau khi chọn (không đợi nhịp 10s)", async () => {
    // Sự cố 16-07: máy hỏng giữa giờ → đáp án chưa kịp nhịp 10s là mất khi đổi máy.
    vi.useFakeTimers();
    try {
      const d = data(600);   // còn nhiều giờ — KHÔNG nằm trong cửa sổ 20s cuối
      const { result } = renderHook(() => useExamSession("s1", d, () => {}, ws));
      act(() => result.current.selectOption("q1", "A"));
      expect(answersBulk).not.toHaveBeenCalled();               // chưa đẩy ngay
      await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
      expect(answersBulk).toHaveBeenCalledTimes(1);             // ~2.5s sau là lên server
      expect(answersBulk).toHaveBeenCalledWith([{ question_id: "q1", selected_option: "A" }]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("AD-88: nhiều lần đổi liên tiếp gộp chung MỘT lô (không dập server)", async () => {
    vi.useFakeTimers();
    try {
      const d = data(600);
      const { result } = renderHook(() => useExamSession("s1", d, () => {}, ws));
      act(() => result.current.selectOption("q1", "A"));
      act(() => result.current.selectOption("q1", "B"));   // đổi ý trong cửa sổ 2.5s
      await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
      expect(answersBulk).toHaveBeenCalledTimes(1);
      expect(answersBulk).toHaveBeenCalledWith([{ question_id: "q1", selected_option: "B" }]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("đẩy đáp án dồn nhịp (~2.5s) ở 20s cuối để kịp về trước end_time", async () => {
    vi.useFakeTimers();
    try {
      const d = data(10);   // sắp hết giờ → nhịp nhanh
      const { result } = renderHook(() => useExamSession("s1", d, () => {}, ws));
      act(() => result.current.selectOption("q1", "A"));
      // Nhịp nhanh ≤ 4s (2.5s + jitter ≤1.5s) → trong 4s đã đẩy ≥1 lần
      // (nhịp thường 10s thì chưa đẩy). Không dồn: mỗi máy lệch pha ngẫu nhiên.
      await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
      expect(answersBulk).toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("AD-90: nộp hỏng mạng → báo lỗi, GIỮ bài local, cho nộp lại", async () => {
    vi.useFakeTimers();
    try {
      submit.mockRejectedValue({ isAxiosError: true, response: undefined });
      const onSubmitted = vi.fn();
      const d = data(600);
      const { result } = renderHook(() => useExamSession("s1", d, onSubmitted, ws));
      act(() => result.current.selectOption("q1", "A"));
      await act(async () => {
        const p = result.current.doSubmit(false);
        // Chỉ tua đủ 2 nhịp chờ giữa các lần thử (1s + 2s) — KHÔNG runAllTimers
        // vì hook có setInterval lặp vô hạn (nhịp đẩy lô / poll trạng thái).
        await vi.advanceTimersByTimeAsync(5000);
        await p;
      });
      expect(submit).toHaveBeenCalledTimes(3);            // thử lại 3 lần
      expect(onSubmitted).not.toHaveBeenCalled();          // KHÔNG chuyển màn kết quả
      expect(result.current.submitError).toContain("Không gửi được bài");
      expect(localStorage.getItem("answers_s1")).not.toBeNull();   // bài vẫn còn
      // Mở khoá: bấm nộp lại chạy thật (lần này server nhận).
      submit.mockResolvedValue({});
      await act(async () => { await result.current.doSubmit(false); });
      expect(onSubmitted).toHaveBeenCalledOnce();
    } finally {
      vi.useRealTimers();
      submit.mockReset(); submit.mockResolvedValue({});
    }
  });

  it("AD-90: server trả 4xx khi nộp mà phiên ĐÃ chốt thật → coi như nộp xong", async () => {
    submit.mockRejectedValueOnce({ isAxiosError: true, response: { status: 409 } });
    // R2: 4xx một mình không đủ kết luận "đã nộp" — phải hỏi lại /state.
    state.mockResolvedValue({ paused: false, time_remaining_seconds: 0, status: "submitted" });
    const onSubmitted = vi.fn();
    const d = data(600);   // GIỮ NGUYÊN object giữa các lần render (đổi = lặp vô hạn)
    const { result } = renderHook(() => useExamSession("s1", d, onSubmitted, ws));
    await act(async () => { await result.current.doSubmit(true); });
    expect(onSubmitted).toHaveBeenCalledOnce();
    expect(result.current.submitError).toBeNull();
    submit.mockReset(); submit.mockResolvedValue({});
  });

  // ── Gói 1: chặn nộp bài thiếu đáp án (R2) + giữ hàng chờ khi 409 (R3) ──────
  // Đây là hai cách hỏng IM LẶNG duy nhất còn lại trên đường nộp bài: chúng cho ra
  // điểm sai mà không để lại triệu chứng nào cho thí sinh, giám thị hay báo cáo.

  it("R2: còn đáp án chưa lên được máy chủ → KHÔNG nộp, báo lỗi, giữ bài trên máy", async () => {
    vi.useFakeTimers();
    try {
      // Mạng chập chờn: mọi cú đẩy đáp án đều hỏng → hàng chờ không bao giờ sạch.
      answersBulk.mockRejectedValue({ isAxiosError: true, response: undefined });
      const onSubmitted = vi.fn();
      const d = data(600);
      const { result } = renderHook(() => useExamSession("s1", d, onSubmitted, ws));
      act(() => result.current.selectOption("q1", "A"));
      await act(async () => {
        const p = result.current.doSubmit(false);
        await vi.advanceTimersByTimeAsync(8000);   // đủ 2 nhịp chờ giữa các lần đẩy lại
        await p;
      });
      // Cốt lõi: KHÔNG được gửi lệnh nộp khi server chưa có đủ đáp án.
      expect(submit).not.toHaveBeenCalled();
      expect(onSubmitted).not.toHaveBeenCalled();
      expect(result.current.submitError).toContain("chưa lưu được lên máy chủ");
      expect(localStorage.getItem("answers_s1")).not.toBeNull();   // bài vẫn còn
    } finally {
      vi.useRealTimers();
    }
  });

  it("R3: 409 (hết giờ/tạm dừng) KHÔNG làm mất đáp án trong hàng chờ", async () => {
    vi.useFakeTimers();
    try {
      answersBulk.mockRejectedValueOnce({ isAxiosError: true, response: { status: 409 } });
      const d = data(600);
      const { result } = renderHook(() => useExamSession("s1", d, () => {}, ws));
      act(() => result.current.selectOption("q1", "A"));
      await act(async () => { await vi.advanceTimersByTimeAsync(3000); });   // debounce → 409
      expect(answersBulk).toHaveBeenCalledTimes(1);
      // Hàng chờ CHƯA sạch thì chỉ báo phải nói thật, không được ghi "Đã lưu".
      expect(result.current.saveStatus).toBe("saving");
      // Nhịp kế tiếp phải đẩy LẠI đúng đáp án đó (sau khi được tiếp tục/cộng giờ).
      await act(async () => { await vi.advanceTimersByTimeAsync(11000); });
      expect(answersBulk).toHaveBeenCalledTimes(2);
      expect(answersBulk).toHaveBeenLastCalledWith([{ question_id: "q1", selected_option: "A" }]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("R2: hàng chờ tắc VÌ server đã chốt phiên → sang màn kết quả, không báo lỗi oan", async () => {
    vi.useFakeTimers();
    try {
      // Giám thị vừa Đóng buổi: /answers/bulk trả 409 mãi vì phiên không còn
      // in_progress. Chặn nộp lúc này là bắt thí sinh xem một lỗi vô nghĩa.
      answersBulk.mockRejectedValue({ isAxiosError: true, response: { status: 409 } });
      state.mockResolvedValue({ paused: false, time_remaining_seconds: 0, status: "submitted" });
      const onSubmitted = vi.fn();
      const d = data(600);
      const { result } = renderHook(() => useExamSession("s1", d, onSubmitted, ws));
      act(() => result.current.selectOption("q1", "A"));
      await act(async () => {
        const p = result.current.doSubmit(false);
        await vi.advanceTimersByTimeAsync(8000);
        await p;
      });
      expect(onSubmitted).toHaveBeenCalledOnce();
      expect(result.current.submitError).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("R2: nộp trả 4xx mà server nói phiên CHƯA chốt → báo lỗi, KHÔNG xoá bài", async () => {
    // 409 của /submit có thể là "chưa tới giờ bắt đầu" — không phải "đã nộp rồi".
    // Tin nhầm là xoá bài trên máy rồi đẩy thí sinh sang màn kết quả trống.
    submit.mockRejectedValue({ isAxiosError: true, response: { status: 409 } });
    state.mockResolvedValue({ paused: false, time_remaining_seconds: 600, status: "in_progress" });
    const onSubmitted = vi.fn();
    const d = data(600);
    const { result } = renderHook(() => useExamSession("s1", d, onSubmitted, ws));
    act(() => result.current.selectOption("q1", "A"));
    await act(async () => { await result.current.doSubmit(false); });
    expect(onSubmitted).not.toHaveBeenCalled();
    expect(localStorage.getItem("answers_s1")).not.toBeNull();
    expect(result.current.submitError).toBeTruthy();
    submit.mockReset(); submit.mockResolvedValue({});
  });

  it("R1: đang gửi bài thì hook báo `submitting` (để giao diện khoá nút + hiện tiến trình)", async () => {
    let release: () => void = () => {};
    submit.mockImplementation(() => new Promise<void>((r) => { release = () => r(); }));
    const d = data(600);
    const { result } = renderHook(() => useExamSession("s1", d, () => {}, ws));
    await act(async () => { void result.current.doSubmit(false); });
    expect(result.current.submitting).toBe(true);
    await act(async () => { release(); });
    expect(result.current.submitting).toBe(false);
    submit.mockReset(); submit.mockResolvedValue({});
  });

  it("AD-90b: selectOption giữ nguyên danh tính giữa các lần vẽ lại (để memo có tác dụng)", () => {
    const d = data(600);
    const { result, rerender } = renderHook(() => useExamSession("s1", d, () => {}, ws));
    const first = result.current.selectOption;
    rerender();                                  // ví dụ: đồng hồ nhảy 1 giây
    expect(result.current.selectOption).toBe(first);
    // Vẫn chạy đúng sau khi rerender (không ôm state cũ).
    act(() => result.current.selectOption("q1", "A"));
    expect(result.current.answers).toEqual({ q1: "A" });
  });

  it("locks input when time is up (no answer change, no save)", () => {
    const d = data(0);
    const { result } = renderHook(() => useExamSession("s1", d, () => {}, ws));
    expect(result.current.timeUp).toBe(true);
    act(() => result.current.selectOption("q1", "A"));
    expect(result.current.answers).toEqual({});
    expect(answersBulk).not.toHaveBeenCalled();
  });
});
