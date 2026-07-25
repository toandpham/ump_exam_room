/** usePreloadDeck (AD-110) — tách khỏi App.tsx ở refactor đợt 3.
 * Khoá semantics: báo `preload-done` ĐÚNG 1 LẦN mỗi phiên khi tải đủ; đổi phiên
 * thì báo lại; lỗi mạng thì thử lại. Gate "Bắt đầu thi" bên chủ tịch phụ thuộc
 * đúng cờ này nên đây là hợp đồng không được vỡ khi refactor tiếp. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

const preloadDone = vi.fn().mockResolvedValue({ ok: true });
vi.mock("../api/exam", () => ({ examApi: { preloadDone: () => preloadDone() } }));

/** Ảnh giả: báo onload ở tick kế (không đụng mạng thật). */
class FakeImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  set src(_v: string) { setTimeout(() => this.onload?.(), 0); }
}

import { usePreloadDeck } from "./usePreloadDeck";

const deck = (n: number) => ({
  status: "ready", time_remaining_seconds: null, total: n, answers: {},
  questions: Array.from({ length: n }, (_, i) => ({
    id: `q${i}`, text: "t", images: [`/uploads/${i}.jpg`], options: [],
  })),
}) as any;

beforeEach(() => {
  // mockReset + set lại impl: restoreAllMocks() sẽ xoá cả implementation khiến
  // preloadDone trả undefined ở test sau (mất .catch) — bug này từng làm test đỏ.
  preloadDone.mockReset();
  preloadDone.mockResolvedValue({ ok: true });
  (globalThis as any).Image = FakeImage as unknown as typeof Image;
});
afterEach(() => vi.useRealTimers());

// QUAN TRỌNG: object đề phải ỔN ĐỊNH giữa các lần render — tạo mới trong
// renderHook sẽ đổi identity mỗi render → effect chạy lại vô hạn → OOM.
const DECK3 = deck(3);
const DECK1 = deck(1);
const DECK2 = deck(2);
const DECK_NO_IMG = { ...deck(0), questions: [{ id: "q", text: "t", images: [], options: [] }] };

describe("usePreloadDeck", () => {
  it("tải đủ → báo preload-done ĐÚNG 1 lần + trả tiến độ done/total", async () => {
    const { result } = renderHook(() =>
      usePreloadDeck("ready", "sess-1", DECK3));
    await waitFor(() => expect(result.current.download?.done).toBe(3));
    expect(result.current.download).toEqual({ done: 3, total: 3 });
    await waitFor(() => expect(preloadDone).toHaveBeenCalledTimes(1));
  });

  it("đề KHÔNG có ảnh (0/0) vẫn coi là tải xong → vẫn báo server", async () => {
    renderHook(() => usePreloadDeck("ready", "sess-2", DECK_NO_IMG));
    await waitFor(() => expect(preloadDone).toHaveBeenCalledTimes(1));
  });

  it("KHÔNG báo khi chưa 'ready' (vd đang chờ phát đề)", async () => {
    renderHook(() => usePreloadDeck("waiting", "sess-3", DECK2));
    await new Promise((r) => setTimeout(r, 30));
    expect(preloadDone).not.toHaveBeenCalled();
  });

  it("lỗi mạng → thử lại (không kẹt vĩnh viễn ở 'chưa tải xong')", async () => {
    vi.useFakeTimers();
    preloadDone.mockRejectedValueOnce(new Error("network"));
    renderHook(() => usePreloadDeck("ready", "sess-4", DECK1));
    await vi.advanceTimersByTimeAsync(10);
    expect(preloadDone).toHaveBeenCalledTimes(1);   // lần đầu — hỏng
    await vi.advanceTimersByTimeAsync(5100);        // hẹn giờ thử lại
    expect(preloadDone).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });
});
