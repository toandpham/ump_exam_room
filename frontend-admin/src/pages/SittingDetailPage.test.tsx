/** Chốt chặn "Đóng buổi" (lỗ AD-121 #1).
 *
 * Nút này ép nộp mọi bài đang làm. Trước đây hộp xác nhận không hề nói còn bao
 * nhiêu người chưa xong, nên bấm sớm là cắt bài giữa chừng mà chẳng ai biết. Test
 * khoá đúng hai điều: hộp xác nhận phải NÊU SỐ NGƯỜI, và chỉ khi đó mới được gửi
 * cờ ``force`` (nếu không thì máy chủ trả 409 — chốt chặn thứ hai). */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SittingDetailPage from "./SittingDetailPage";
import type { SessionSummary } from "../api/monitor";

const endFn = vi.fn(async () => ({ submitted: 0 }));
const sessionsFn = vi.fn(async (): Promise<SessionSummary[]> => []);

vi.mock("../api/sittings", () => ({
  sittingsApi: {
    get: async () => ({
      id: "s1", name: "Buổi 1", status: "active", has_payload: true,
      question_count: 10, duration_minutes: 45, has_running_sessions: true,
    }),
    sessions: (id: string) => sessionsFn(id),
    open: vi.fn(),
    end: (id: string, force: boolean) => endFn(id, force),
  },
}));

function sess(over: Partial<SessionSummary>): SessionSummary {
  return {
    session_id: Math.random().toString(), candidate_id: "c", cccd: "079111111111",
    full_name: "Nguyễn Văn A", unit: "U", category: "SV", attempt_number: 1,
    photo_path: null, status: "in_progress", submitted_at: null, end_time: null,
    paused: false, overdue_paused: false, self_registered: false,
    room_id: null, room_name: "P1", preloaded: true, info_disputed: false,
    offline: false, last_seen_seconds: 1, score: null, total_correct: null,
    client_ip: null, device_id: null, started_at: null,
    ...over,
  } as SessionSummary;
}

const inFuture = () => new Date(Date.now() + 20 * 60_000).toISOString();
const inPast = () => new Date(Date.now() - 5 * 60_000).toISOString();

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/exams/e1/sittings/s1/monitor"]}>
        <Routes>
          <Route path="/exams/:examId/sittings/:sittingId/*" element={<SittingDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Đóng buổi — không cắt bài người còn giờ", () => {
  beforeEach(() => {
    endFn.mockClear();
    sessionsFn.mockClear();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("còn người đang làm bài → hộp xác nhận nêu rõ số người và cảnh báo cắt bài", async () => {
    sessionsFn.mockResolvedValue([
      sess({ end_time: inFuture() }),
      sess({ end_time: inFuture() }),
      sess({ status: "submitted", end_time: inPast() }),
    ]);
    mount();
    await screen.findByText("Buổi 1");
    await waitFor(() => expect(screen.getByText(/còn 2 thí sinh chưa xong/)).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: /Đóng buổi/ }));
    const msg = (window.confirm as any).mock.calls[0][0] as string;
    expect(msg).toContain("2 thí sinh CÒN GIỜ");
    expect(msg).toContain("CẮT BÀI GIỮA CHỪNG");
    await waitFor(() => expect(endFn).toHaveBeenCalledWith("s1", true));
  });

  it("người đang tạm dừng cũng được đếm — họ chưa hết giờ, chỉ đang bị dừng", async () => {
    sessionsFn.mockResolvedValue([
      sess({ paused: true, overdue_paused: true, end_time: inPast() }),
    ]);
    mount();
    await screen.findByText("Buổi 1");
    await waitFor(() => expect(screen.getByText(/còn 1 thí sinh chưa xong/)).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: /Đóng buổi/ }));
    expect((window.confirm as any).mock.calls[0][0]).toContain("1 thí sinh đang TẠM DỪNG");
  });

  it("mọi người đã xong → xác nhận bình thường, KHÔNG gửi cờ bỏ qua", async () => {
    sessionsFn.mockResolvedValue([sess({ status: "submitted", end_time: inPast() })]);
    mount();
    await screen.findByText("Buổi 1");
    fireEvent.click(screen.getByRole("button", { name: /Đóng buổi/ }));

    const msg = (window.confirm as any).mock.calls[0][0] as string;
    expect(msg).not.toContain("CẮT BÀI");
    await waitFor(() => expect(endFn).toHaveBeenCalledWith("s1", false));
  });

  it("người dùng bấm Huỷ thì không đóng gì cả", async () => {
    (window.confirm as any).mockReturnValue(false);
    sessionsFn.mockResolvedValue([sess({ end_time: inFuture() })]);
    mount();
    await screen.findByText("Buổi 1");
    fireEvent.click(screen.getByRole("button", { name: /Đóng buổi/ }));
    expect(endFn).not.toHaveBeenCalled();
  });
});
