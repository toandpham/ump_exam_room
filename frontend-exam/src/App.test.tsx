import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { useStore } from "./store";

// Bug thực địa 13-07: thí sinh đổi máy / vào trễ / reload giữa lúc đếm ngược bị
// KẸT vĩnh viễn ở màn "Đề đã sẵn sàng" với số 0. Nguyên nhân: effect reset
// setStarted(false) theo [session_id] (cha) chạy SAU onStart của CountdownScreen
// (con) trong cùng commit mount → đè mất cờ started, còn firedRef của countdown
// đã true nên không bao giờ bắn lại.

const CANDIDATE = {
  id: "c1", cccd: "111111111111", full_name: "Test TS", birth_date: "2000-01-01",
  unit: "A", major: null, category: "B", attempt_number: 1, photo_path: null,
};

vi.mock("./api/exam", () => ({
  examApi: {
    status: vi.fn(async () => ({ open: true, exam_name: "Kỳ thi", allow_registration: false })),
    me: vi.fn(async () => ({ candidate: CANDIDATE, exam: { id: "e1", name: "Kỳ thi", duration_minutes: 60, exam_date: null } })),
    // Phiên ĐANG THI, mốc bắt đầu đã qua 30s (đúng cảnh reconnect sau "Bắt đầu thi").
    state: vi.fn(async () => ({
      session_id: "s1",
      status: "in_progress",
      started_at: new Date(Date.now() - 30000).toISOString(),
      end_time: new Date(Date.now() + 3600000).toISOString(),
      submitted_at: null,
      server_time: new Date().toISOString(),
      time_remaining_seconds: 3600,
      paused: false,
    })),
    questions: vi.fn(async () => ({ questions: [], total: 0 })),
  },
}));

vi.mock("./hooks/useExamSocket", () => ({
  useExamSocket: () => ({ send: vi.fn() }),
}));

// ExamScreen thật cần đề/đồng hồ — thay bằng mốc đánh dấu, đủ để test wiring.
vi.mock("./screens/ExamScreen", () => ({
  default: () => <div>EXAM_SCREEN</div>,
}));

function renderApp() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>
  );
}

describe("ExamShell — reconnect khi buổi đã bắt đầu (SP-2c)", () => {
  beforeEach(() => {
    useStore.setState({ token: "tok", candidate: null, exam: null });
  });

  it("đăng nhập lại giữa giờ → vào thẳng đề, không kẹt màn đếm ngược", async () => {
    renderApp();
    // Nếu dính race, màn hình dừng ở "Đề đã sẵn sàng — chuẩn bị bắt đầu" với số 0.
    expect(await screen.findByText("EXAM_SCREEN", {}, { timeout: 3000 })).toBeTruthy();
  });
});
