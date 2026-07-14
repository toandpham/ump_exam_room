import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

const logout = vi.fn();
vi.mock("../store", () => ({
  useStore: () => ({ candidate: null, exam: null, logout }),
  photoUrl: () => undefined,
}));
vi.mock("../api/exam", () => ({
  examApi: {
    result: vi.fn().mockResolvedValue({
      status: "submitted", submitted_at: null, total: 2, answered: 2, total_correct: 1,
    }),
  },
}));

import StatusScreen from "./StatusScreen";

describe("StatusScreen auto-logout (AD-69)", () => {
  beforeEach(() => { logout.mockClear(); vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("auto-logs out 30s after showing the result", async () => {
    render(<StatusScreen variant="result" />);
    await vi.advanceTimersByTimeAsync(29000);
    expect(logout).not.toHaveBeenCalled();   // còn 1s
    await vi.advanceTimersByTimeAsync(1000);
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it("does NOT auto-logout on waiting/ready screens", async () => {
    render(<StatusScreen variant="waiting" />);
    await vi.advanceTimersByTimeAsync(60000);
    expect(logout).not.toHaveBeenCalled();
  });

  it("'Đăng xuất ngay' logs out immediately", async () => {
    render(<StatusScreen variant="result" />);
    await vi.advanceTimersByTimeAsync(0);   // flush the result fetch
    fireEvent.click(screen.getByText(/Đăng xuất ngay/));
    expect(logout).toHaveBeenCalled();
  });
});
