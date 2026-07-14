import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import CountdownScreen from "./CountdownScreen";

describe("CountdownScreen (SP-2c)", () => {
  it("đếm ngược rồi gọi onStart khi tới giờ", () => {
    vi.useFakeTimers();
    const now = new Date("2026-01-01T00:00:00Z");
    vi.setSystemTime(now);
    const onStart = vi.fn();
    const startAt = new Date(now.getTime() + 3000).toISOString();
    const { container } = render(
      <CountdownScreen startAt={startAt} serverTime={now.toISOString()} onStart={onStart} />);
    expect(container.textContent).toContain("3");
    vi.advanceTimersByTime(3300);
    expect(onStart).toHaveBeenCalledOnce();
    vi.useRealTimers();
  });

  it("mở ngay nếu đã qua giờ bắt đầu", () => {
    vi.useFakeTimers();
    const now = new Date("2026-01-01T00:00:00Z");
    vi.setSystemTime(now);
    const onStart = vi.fn();
    const startAt = new Date(now.getTime() - 1000).toISOString();
    render(<CountdownScreen startAt={startAt} serverTime={now.toISOString()} onStart={onStart} />);
    vi.advanceTimersByTime(20);
    expect(onStart).toHaveBeenCalledOnce();
    vi.useRealTimers();
  });

  it("neo theo giờ server dù đồng hồ máy lệch (máy chậm 60s)", () => {
    vi.useFakeTimers();
    const clientNow = new Date("2026-01-01T00:00:00Z");
    vi.setSystemTime(clientNow);
    const onStart = vi.fn();
    const serverTime = new Date(clientNow.getTime() + 60000).toISOString(); // server nhanh hơn máy 60s
    const startAt = new Date(clientNow.getTime() + 63000).toISOString();     // = serverTime + 3s
    render(<CountdownScreen startAt={startAt} serverTime={serverTime} onStart={onStart} />);
    vi.advanceTimersByTime(3300);   // 3s theo giờ máy → chạm mốc server → mở
    expect(onStart).toHaveBeenCalledOnce();
    vi.useRealTimers();
  });
});
