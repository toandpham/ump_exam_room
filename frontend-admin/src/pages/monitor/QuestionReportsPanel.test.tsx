/** Hộp khiếu nại câu hỏi (đợt 3).
 *
 * Hội đồng phải biết NGAY khi có người báo "câu 47 thiếu hình" — chờ tới lúc chấm
 * mới đọc là đã muộn. Và phải còn đọc được sau khi đóng buổi, vì đó mới là lúc chấm.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import QuestionReportsPanel from "./QuestionReportsPanel";
import type { QuestionReport } from "../../api/monitor";

const listFn = vi.fn(async (): Promise<QuestionReport[]> => []);
const resolveFn = vi.fn(async () => ({ resolved: true }));

vi.mock("../../api/monitor", () => ({
  monitorApi: {
    questionReports: (id: string) => listFn(id),
    resolveQuestionReport: (id: string, r: string) => resolveFn(id, r),
  },
}));

function report(over: Partial<QuestionReport> = {}): QuestionReport {
  return {
    id: "r1", candidate_id: "c1", cccd: "079000000001", full_name: "Lê Thị B",
    room_name: "Phòng 2", question_id: "q1", question_number: 47,
    content: "Câu này thiếu hình chụp X-quang",
    created_at: new Date().toISOString(),
    resolved_at: null, resolution: null, resolved_by_name: null,
    ...over,
  };
}

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}><QuestionReportsPanel sittingId="s1" /></QueryClientProvider>,
  );
}

describe("QuestionReportsPanel", () => {
  beforeEach(() => { listFn.mockClear(); resolveFn.mockClear(); });

  it("không có khiếu nại thì không chiếm chỗ", async () => {
    listFn.mockResolvedValue([]);
    const { container } = mount();
    await waitFor(() => expect(listFn).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("hiện số câu, tên thí sinh, phòng và nội dung", async () => {
    listFn.mockResolvedValue([report()]);
    mount();
    await screen.findByText(/Câu 47/);
    expect(screen.getByText(/thiếu hình chụp X-quang/)).toBeTruthy();
    expect(screen.getByText(/Lê Thị B/)).toBeTruthy();
    expect(screen.getByText(/Phòng 2/)).toBeTruthy();
    expect(screen.getByText(/1 khiếu nại về câu hỏi chưa xử lý/)).toBeTruthy();
  });

  it("đã xử lý thì hiện kết luận và không còn nút xử lý", async () => {
    listFn.mockResolvedValue([report({
      resolved_at: new Date().toISOString(),
      resolution: "Đã kiểm tra, đề đúng", resolved_by_name: "Chủ tịch A",
    })]);
    mount();
    await screen.findByText(/Câu 47/);
    expect(screen.getByText(/Đã kiểm tra, đề đúng/)).toBeTruthy();
    expect(screen.queryByText("Đã xử lý")).toBeNull();
    expect(screen.getByText(/đã xử lý hết/)).toBeTruthy();
  });
});
