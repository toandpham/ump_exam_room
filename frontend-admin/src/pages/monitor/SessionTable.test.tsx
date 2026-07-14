import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import SessionTable from "./SessionTable";
import type { SessionSummary } from "../../api/monitor";
import type { DisplayRow } from "./constants";

function session(over: Partial<SessionSummary> = {}): SessionSummary {
  return {
    session_id: "s1", candidate_id: "c1", cccd: "079000000001", full_name: "Trần Văn A",
    unit: "Đơn vị 1", category: "ĐT1", attempt_number: 1, photo_path: null,
    status: "in_progress", paused: false,
    self_registered: false, room_id: null, room_name: null, ...over,
  };
}

const noop = () => {};

describe("SessionTable", () => {
  it("renders a logged-in session and a pending candidate", () => {
    const rows: DisplayRow[] = [
      { kind: "session", s: session() },
      { kind: "pending", c: { candidate_id: "c2", cccd: "079000000002", full_name: "Lê Thị B", unit: "Đơn vị 2", category: "ĐT1", attempt_number: 1, photo_path: null, self_registered: false, room_name: "Phòng 2" } },
    ];
    const { container } = render(<SessionTable rows={rows} onLogout={noop} onAdmit={noop} />);
    expect(container.textContent).toContain("STT");          // sequence-number column
    expect(container.textContent).toContain("Trần Văn A");
    expect(container.textContent).toContain("Đang làm");      // status label
    expect(container.textContent).toContain("Lê Thị B");
    expect(container.textContent).toContain("Chưa đăng nhập");
    expect(container.textContent).toContain("Phòng 2"); // assigned room shows even before login
    // STT đánh số 1-based theo thứ tự dòng
    const cells = container.querySelectorAll("tbody tr td:first-child");
    expect(cells[0].textContent).toBe("1");
    expect(cells[1].textContent).toBe("2");
  });

  it("shows 'Duyệt vào thi' only for waiting/ready, and logout calls back with the session", () => {
    const onLogout = vi.fn();
    const waiting = session({ status: "waiting" });
    const r1 = render(<SessionTable rows={[{ kind: "session", s: waiting }]} onLogout={onLogout} onAdmit={noop} />);
    expect(r1.container.textContent).toContain("Duyệt vào thi");
    r1.getByText("Đăng xuất").click();
    expect(onLogout).toHaveBeenCalledWith(waiting);

    const r2 = render(<SessionTable rows={[{ kind: "session", s: session({ status: "in_progress" }) }]} onLogout={noop} onAdmit={noop} />);
    expect(r2.container.textContent).not.toContain("Duyệt vào thi");
  });

  it("nút Duyệt vào thi cho ready: bật khi buổi đang chạy (hasRunning=true)", () => {
    // hasRunning=true → thí sinh ready xác nhận SAU khi "Bắt đầu thi" → nút bật (enabled)
    const ready = session({ status: "ready" });
    const { getByRole } = render(<SessionTable rows={[{ kind: "session", s: ready }]} onLogout={noop} onAdmit={noop} hasRunning />);
    const btn = getByRole("button", { name: /Duyệt vào thi/ }) as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("nút Duyệt vào thi cho ready: mờ khi chưa bắt đầu (hasRunning=false)", () => {
    // hasRunning=false (hoặc undefined) → chưa bắt đầu, cả phòng vào cùng lúc → nút mờ (disabled)
    const ready = session({ status: "ready" });
    const { getByRole } = render(<SessionTable rows={[{ kind: "session", s: ready }]} onLogout={noop} onAdmit={noop} hasRunning={false} />);
    const btn = getByRole("button", { name: /Duyệt vào thi/ }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("không còn hiển thị chỉ báo kết nối (đã gỡ AD-38)", () => {
    const { container } = render(
      <SessionTable rows={[{ kind: "session", s: session({}) }]} onLogout={noop} onAdmit={noop} />,
    );
    expect(container.textContent).not.toContain("mất kết nối");
  });
});
