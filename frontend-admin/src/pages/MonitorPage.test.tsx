/** Gate "Bắt đầu thi" theo tiến độ tải đề (AD-110) — lưới an toàn refactor đợt 3 (T0.3).
 * Logic: nút chỉ enabled khi MỌI session ready có preloaded=true; thiếu máy → nút
 * disabled + hiện van "Vẫn bắt đầu (bỏ qua N máy chưa tải đề)". */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route, Outlet } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import MonitorPage from "./MonitorPage";
import type { SessionSummary } from "../api/monitor";

const sessionsFn = vi.fn(async (): Promise<SessionSummary[]> => []);
const rosterFn = vi.fn(async () => ROSTER);

vi.mock("../api/sittings", () => ({
  sittingsApi: {
    sessions: (id: string) => sessionsFn(id),
    roster: (id: string) => rosterFn(id),
    start: vi.fn(), pauseAll: vi.fn(), resumeAll: vi.fn(),
  },
}));
vi.mock("../api/monitor", () => ({
  monitorApi: { logout: vi.fn(), admit: vi.fn(), pauseSession: vi.fn(), resumeSession: vi.fn() },
}));

const ROSTER = {
  earliest_end_time: null, server_time: new Date().toISOString(),
  assigned_total: 2, logged_in: 2, not_logged_in_total: 0, not_logged_in: [],
  question_count: 10,
};

function sess(over: Partial<SessionSummary>): SessionSummary {
  return {
    session_id: Math.random().toString(), candidate_id: "c", cccd: "079111111111",
    full_name: "Nguyễn Văn A", unit: "U", category: "SV", attempt_number: 1,
    photo_path: null, status: "ready", submitted_at: null, paused: false,
    self_registered: false, room_id: null, room_name: "P1", preloaded: true,
    ...over,
  } as SessionSummary;
}

const SITTING = { id: "s1", status: "active", has_payload: true, name: "Buổi 1" } as any;

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/x"]}>
        <Routes>
          <Route element={<Outlet context={{ examId: "e1", sittingId: "s1", sitting: SITTING }} />}>
            <Route path="/x" element={<MonitorPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const startBtn = () =>
  screen.getAllByRole("button").find((b) => b.textContent?.includes("Bắt đầu thi"))!;

describe("MonitorPage — gate Bắt đầu thi (AD-110)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("mọi máy ready đã tải đề → nút ENABLED, không có van bỏ qua", async () => {
    sessionsFn.mockResolvedValue([sess({ preloaded: true }), sess({ preloaded: true })]);
    mount();
    // Chờ dữ liệu sessions về (render đầu chưa có → nút disabled tạm thời).
    await waitFor(() => expect((startBtn() as HTMLButtonElement).disabled).toBe(false));
    expect(screen.queryByText(/Vẫn bắt đầu/)).toBeNull();
    expect(screen.getByText(/2\/2/)).toBeTruthy();   // "đề đã tải đủ 2/2 máy"
  });

  it("còn máy chưa tải đề → nút DISABLED + van 'Vẫn bắt đầu (bỏ qua 1 máy…)' + đếm 1/2", async () => {
    sessionsFn.mockResolvedValue([sess({ preloaded: true }), sess({ preloaded: false })]);
    mount();
    await waitFor(() => expect(screen.queryByText(/Vẫn bắt đầu/)).toBeTruthy());
    expect((startBtn() as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/bỏ qua 1 máy chưa tải đề/)).toBeTruthy();
    expect(screen.getByText(/1\/2/)).toBeTruthy();   // "Đã tải đề 1/2 máy"
  });

  it("chưa có máy nào sẵn sàng → nút DISABLED, không có van", async () => {
    sessionsFn.mockResolvedValue([sess({ status: "waiting", preloaded: false })]);
    mount();
    await waitFor(() => expect(startBtn()).toBeTruthy());
    expect((startBtn() as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText(/Vẫn bắt đầu/)).toBeNull();
  });
});
