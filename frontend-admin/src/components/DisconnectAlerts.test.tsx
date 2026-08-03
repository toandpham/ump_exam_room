import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import DisconnectAlerts from "./DisconnectAlerts";

const row = (over: Partial<Parameters<typeof DisconnectAlerts>[0]["rows"][0]> = {}) => ({
  key: "s1", full_name: "Nguyễn Văn A", cccd: "012345678901",
  room_name: "Phòng 1", last_seen_seconds: 150, ...over,
});

describe("DisconnectAlerts", () => {
  it("ẩn hoàn toàn khi không có ai mất kết nối", () => {
    const { container } = render(<DisconnectAlerts rows={[]} />);
    expect(container.textContent).toBe("");
  });

  it("gom mọi thí sinh mất kết nối lên đầu, kèm tên/CCCD/phòng/thời lượng", () => {
    const { container } = render(
      <DisconnectAlerts rows={[row(), row({ key: "s2", full_name: "Trần B", cccd: "099999999999" })]} />,
    );
    expect(container.textContent).toContain("2 thí sinh đang MẤT KẾT NỐI");
    expect(container.textContent).toContain("Nguyễn Văn A");
    expect(container.textContent).toContain("Trần B");
    expect(container.textContent).toContain("Phòng 1");
    expect(container.textContent).toContain("mất kết nối 2 phút");
  });

  it("nói rõ bài làm không mất, để giám thị không hoảng", () => {
    const { container } = render(<DisconnectAlerts rows={[row()]} />);
    expect(container.textContent).toContain("Bài làm đã lưu vẫn còn");
  });
});
