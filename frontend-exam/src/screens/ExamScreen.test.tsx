import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";

/** Trạng thái phiên thi do test điều khiển — ta chỉ kiểm QUYẾT ĐỊNH HIỂN THỊ của
 * màn thi, không kiểm lại logic của hook (đã có test riêng). */
const session: Record<string, unknown> = {};
function resetSession() {
  Object.assign(session, {
    answers: {}, selectOption: vi.fn(), flags: {}, toggleFlag: vi.fn(),
    saveStatus: "saved", secondsLeft: 600, paused: false, timeUp: false,
    doSubmit: vi.fn(), submitting: false, tabCount: 0,
    submitError: null, clearSubmitError: vi.fn(),
    reportQuestion: vi.fn(), markViewed: vi.fn(),
  });
}
resetSession();

vi.mock("../hooks/useExamSession", () => ({ useExamSession: () => session }));
vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({
    data: {
      status: "in_progress", time_remaining_seconds: 600, total: 1, answers: {},
      questions: [{ id: "q1", text: "Câu 1", images: [], options: [{ id: "A", text: "a", images: [] }] }],
    },
  }),
}));
vi.mock("../api/exam", () => ({ examApi: {} }));
vi.mock("../lib/preload", () => ({ PRELOAD_AHEAD: 3, imageUrlsOf: () => [], preloadImages: () => {} }));

import ExamScreen from "./ExamScreen";

const ws = { send: vi.fn(), subscribe: vi.fn(() => () => {}) };
const renderScreen = () =>
  render(<ExamScreen sessionId="s1" onSubmitted={() => {}} ws={ws} />);

beforeEach(resetSession);

describe("ExamScreen", () => {
  it("R1: đang gửi bài → hiện lớp phủ để thí sinh biết máy đang làm việc", () => {
    // Trước đây hộp thoại xác nhận đóng lại NGAY và không có phản hồi nào; nếu cú
    // nộp treo thì thí sinh ngồi trước màn hình bài thi, tưởng đã nộp xong.
    session.submitting = true;
    const { container } = renderScreen();
    expect(container.textContent).toContain("Đang gửi bài");
  });

  it("không gửi bài thì KHÔNG hiện lớp phủ đó", () => {
    const { container } = renderScreen();
    expect(container.textContent).not.toContain("Đang gửi bài");
  });
});
