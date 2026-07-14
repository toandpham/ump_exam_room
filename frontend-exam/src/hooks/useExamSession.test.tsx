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
  answer.mockClear(); answersBulk.mockClear(); submit.mockClear();
  answersBulk.mockResolvedValue({ saved: 1 });
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

  it("drops the batch on HTTP 4xx (no permanent 'Mất kết nối')", async () => {
    answersBulk.mockRejectedValueOnce({ isAxiosError: true, response: { status: 409 } });
    const d = data(60);
    const { result } = renderHook(() => useExamSession("s1", d, () => {}, ws));
    act(() => result.current.selectOption("q1", "A"));
    await act(async () => { await result.current.doSubmit(true); });
    expect(result.current.saveStatus).toBe("saved");   // 409 = từ chối vĩnh viễn → bỏ
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

  it("locks input when time is up (no answer change, no save)", () => {
    const d = data(0);
    const { result } = renderHook(() => useExamSession("s1", d, () => {}, ws));
    expect(result.current.timeUp).toBe(true);
    act(() => result.current.selectOption("q1", "A"));
    expect(result.current.answers).toEqual({});
    expect(answersBulk).not.toHaveBeenCalled();
  });
});
