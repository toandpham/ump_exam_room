import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act, render } from "@testing-library/react";
import ExamCountdown from "./ExamCountdown";

describe("ExamCountdown", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("endTime null → 'Chưa bắt đầu'", () => {
    const { container } = render(<ExamCountdown endTime={null} serverTime={null} />);
    expect(container.textContent).toContain("Chưa bắt đầu");
  });

  it("hiển thị thời gian còn lại, neo theo giờ server", () => {
    // Giờ máy = 12:00:00; server báo 12:00:00; hết giờ lúc 12:30:00 → còn 30:00.
    vi.setSystemTime(new Date("2026-07-14T12:00:00Z"));
    const { container } = render(
      <ExamCountdown endTime="2026-07-14T12:30:00Z" serverTime="2026-07-14T12:00:00Z" />,
    );
    expect(container.textContent).toContain("30:00");
  });

  it("bù lệch đồng hồ máy admin (skew)", () => {
    // Máy admin nhanh 10 phút so với server → vẫn phải tính theo server.
    vi.setSystemTime(new Date("2026-07-14T12:10:00Z")); // máy admin
    const { container } = render(
      <ExamCountdown endTime="2026-07-14T12:30:00Z" serverTime="2026-07-14T12:00:00Z" />,
    );
    // Theo server còn 30:00 (không phải 20:00 theo máy admin lệch).
    expect(container.textContent).toContain("30:00");
  });

  it("quá hạn → 'Đã hết giờ'", () => {
    vi.setSystemTime(new Date("2026-07-14T12:40:00Z"));
    const { container } = render(
      <ExamCountdown endTime="2026-07-14T12:30:00Z" serverTime="2026-07-14T12:40:00Z" />,
    );
    expect(container.textContent).toContain("Đã hết giờ");
  });

  it("đếm lùi mỗi giây", () => {
    vi.setSystemTime(new Date("2026-07-14T12:00:00Z"));
    const { container } = render(
      <ExamCountdown endTime="2026-07-14T12:01:00Z" serverTime="2026-07-14T12:00:00Z" />,
    );
    expect(container.textContent).toContain("01:00");
    act(() => { vi.advanceTimersByTime(1000); });
    expect(container.textContent).toContain("00:59");
  });
});
