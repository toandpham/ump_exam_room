import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, Outlet } from "react-router-dom";
import type { Exam, Room, Sitting } from "../../api/types";

// Mock the three data sources OverviewTab reads. Each test sets return values.
const listSittings = vi.fn();
const listRooms = vi.fn();
const listCandidates = vi.fn();
vi.mock("../../api/sittings", () => ({ sittingsApi: { list: (...a: unknown[]) => listSittings(...a) } }));
vi.mock("../../api/rooms", () => ({ roomsApi: { listRooms: (...a: unknown[]) => listRooms(...a) } }));
vi.mock("../../api/candidates", () => ({ candidatesApi: { list: (...a: unknown[]) => listCandidates(...a) } }));

import OverviewTab from "./OverviewTab";

const exam: Exam = {
  id: "e1", name: "Kỳ thi thử", description: null, duration_minutes: 60,
  exam_date: "2026-06-03", status: "active", question_count: 0, sitting_count: 1,
  has_running_sessions: false, allow_registration: false,
  created_by_name: "Chủ tịch A", created_at: "", updated_at: "",
};

function room(over: Partial<Room>): Room {
  return { id: "r", exam_id: "e1", name: "Phòng 1", proctor_id: null, capacity: 30,
    proctor_name: null, candidate_count: 0, ...over };
}
function sitting(over: Partial<Sitting>): Sitting {
  return { id: "s", exam_id: "e1", name: "Buổi 1", description: null, scheduled_date: null,
    ordinal: 1, duration_minutes: 60, status: "draft", shuffle_questions: false,
    shuffle_options: false, question_count: 0, has_payload: false,
    has_running_sessions: false, created_at: "", updated_at: "", ...over };
}

function renderOverview() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/exams/e1"]}>
        <Routes>
          <Route path="/exams/:examId" element={<Outlet context={{ examId: "e1", exam }} />}>
            <Route index element={<OverviewTab />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OverviewTab (checklist thiết lập kỳ thi)", () => {
  beforeEach(() => {
    listSittings.mockReset();
    listRooms.mockReset();
    listCandidates.mockReset();
  });

  it("hiển thị 3 bước thiết lập theo đúng flow mới", async () => {
    listSittings.mockResolvedValue([sitting({})]);
    listRooms.mockResolvedValue([]);
    listCandidates.mockResolvedValue({ total: 0, items: [], page: 1, page_size: 1, pages: 0 });

    const { findByText, container } = renderOverview();
    await findByText("Các bước thiết lập kỳ thi");
    const txt = container.textContent ?? "";
    expect(txt).toContain("Phòng thi & gán giám thị");
    expect(txt).toContain("Nhập danh sách thí sinh");
    expect(txt).toContain("Chia phòng");
    // Chưa setup gì → detail phản ánh trạng thái rỗng.
    expect(txt).toContain("Chưa import danh sách");
  });

  it("setup chưa xong: nút 'Vào quản lý buổi thi' ở dạng nhạt (steps chưa đủ)", async () => {
    listSittings.mockResolvedValue([]);
    listRooms.mockResolvedValue([room({ proctor_id: null })]); // phòng chưa gán giám thị
    listCandidates.mockResolvedValue({ total: 0, items: [], page: 1, page_size: 1, pages: 0 });

    const { findByText } = renderOverview();
    const cta = await findByText("Vào quản lý buổi thi");
    // chưa done → không có class nền xanh đậm
    expect(cta.closest("a")?.className).not.toContain("bg-blue-600");
  });

  it("setup đủ 3 bước: checklist hiện số liệu đúng + CTA chuyển sang xanh", async () => {
    listSittings.mockResolvedValue([sitting({ name: "Buổi sáng", question_count: 40, status: "active" })]);
    listRooms.mockResolvedValue([
      room({ id: "r1", name: "Phòng 1", proctor_id: "gt1", proctor_name: "Giám thị 1", candidate_count: 2 }),
      room({ id: "r2", name: "Phòng 2", proctor_id: "gt2", proctor_name: "Giám thị 2", candidate_count: 2 }),
    ]);
    listCandidates.mockResolvedValue({ total: 4, items: [], page: 1, page_size: 1, pages: 4 });

    const { findByText } = renderOverview();
    // Chờ từng dữ liệu phụ thuộc query (findByText retry tới khi async resolve).
    expect(await findByText("2 phòng · 2 đã gán giám thị")).toBeTruthy();
    expect(await findByText("4 thí sinh")).toBeTruthy();
    expect(await findByText(/4\/4 đã có phòng/)).toBeTruthy();
    // Buổi thi list hiển thị buổi đã nạp đề.
    expect(await findByText("Buổi sáng")).toBeTruthy();
    expect(await findByText(/40 câu/)).toBeTruthy();
    // Đủ 3 bước → CTA nền xanh đậm.
    const cta = await findByText("Vào quản lý buổi thi");
    expect(cta.closest("a")?.className).toContain("bg-blue-600");
  });
});
