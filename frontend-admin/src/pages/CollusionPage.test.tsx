/** Trang đối chiếu đáp án (đợt 4).
 *
 * Điều dễ hỏng nhất ở đây KHÔNG phải bảng số liệu mà là cách diễn đạt: nếu trang
 * này trông như một danh sách "đã bắt được gian lận" thì hội đồng sẽ xử oan người.
 * Test khoá phần cảnh báo đó lại.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CollusionPage from "./CollusionPage";
import type { CollusionPair } from "../api/monitor";

const listFn = vi.fn(async (): Promise<CollusionPair[]> => []);
vi.mock("../api/monitor", () => ({ monitorApi: { collusion: (id: string) => listFn(id) } }));

const pair = (over: Partial<CollusionPair> = {}): CollusionPair => ({
  a_candidate_id: "a", a_cccd: "079000000001", a_name: "Trần Văn A",
  b_candidate_id: "b", b_cccd: "079000000002", b_name: "Lê Thị B",
  room_name: "Phòng 3", shared_wrong: 12, wrong_a: 14, wrong_b: 13, ratio: 0.923,
  ...over,
});

function mount(status: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/x"]}>
        <Routes>
          <Route element={<Outlet context={{ examId: "e1", sittingId: "s1", sitting: { status } }} />}>
            <Route path="/x" element={<CollusionPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CollusionPage", () => {
  beforeEach(() => listFn.mockClear());

  it("buổi chưa đóng thì nói rõ phải đóng buổi trước", async () => {
    mount("active");
    expect(await screen.findByText(/sau khi đóng buổi/)).toBeTruthy();
    expect(listFn).not.toHaveBeenCalled();
  });

  it("luôn nói rõ đây là DẤU HIỆU, không phải bằng chứng", async () => {
    listFn.mockResolvedValue([pair()]);
    mount("closed");
    await screen.findByText(/Trần Văn A/);
    expect(screen.getByText(/không phải bằng chứng/)).toBeTruthy();
    expect(screen.getByText(/trùng ngẫu nhiên vẫn xảy ra/)).toBeTruthy();
  });

  it("hiện số câu sai giống nhau, số câu sai của mỗi người và tỉ lệ", async () => {
    listFn.mockResolvedValue([pair()]);
    mount("closed");
    await screen.findByText(/Trần Văn A/);
    expect(screen.getByText("12")).toBeTruthy();
    expect(screen.getByText(/A sai 14 · B sai 13/)).toBeTruthy();
    expect(screen.getByText("92%")).toBeTruthy();
    expect(screen.getByText("Phòng 3")).toBeTruthy();
  });

  it("không có cặp nào thì nói thẳng", async () => {
    listFn.mockResolvedValue([]);
    mount("closed");
    expect(await screen.findByText(/Không có cặp nào vượt ngưỡng/)).toBeTruthy();
  });
});
