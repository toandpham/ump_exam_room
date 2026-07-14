import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import LabReference from "./LabReference";
import { filterGroups, normalizeSearch, LAB_GROUPS } from "../lib/labReference";

describe("labReference data + filter", () => {
  it("normalizeSearch bỏ dấu tiếng Việt + đ", () => {
    expect(normalizeSearch("Urê")).toBe("ure");
    expect(normalizeSearch("Định tính")).toBe("dinh tinh");
  });

  it("filterGroups khớp tên xét nghiệm không phân biệt dấu, loại nhóm rỗng", () => {
    const res = filterGroups(LAB_GROUPS, "creatinin");
    const rows = res.flatMap((g) => g.rows);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((r) => r.test.toLowerCase().includes("creatinin"))).toBe(true);
    // "ure" (không dấu) vẫn khớp "Urê"
    expect(filterGroups(LAB_GROUPS, "ure").flatMap((g) => g.rows).some((r) => r.test === "Urê")).toBe(true);
  });

  it("query rỗng trả về toàn bộ nhóm", () => {
    expect(filterGroups(LAB_GROUPS, "   ")).toHaveLength(LAB_GROUPS.length);
  });
});

describe("LabReference panel", () => {
  it("không render khi đóng", () => {
    const { container } = render(<LabReference open={false} onClose={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it("hiện các chỉ số và lọc theo ô tìm kiếm", () => {
    render(<LabReference open onClose={() => {}} />);
    // Hiển thị chỉ số quen thuộc (Creatinin có 2 dòng: µmol/L & mg/dL)
    expect(screen.getAllByText("Creatinin").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("WBC")).toBeTruthy();

    // Gõ tìm "TSH" → còn TSH, mất WBC
    fireEvent.change(screen.getByPlaceholderText(/Tìm chỉ số/i), { target: { value: "TSH" } });
    expect(screen.getByText("TSH")).toBeTruthy();
    expect(screen.queryByText("WBC")).toBeNull();
  });

  it("hiện thông báo khi không có kết quả", () => {
    render(<LabReference open onClose={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText(/Tìm chỉ số/i), { target: { value: "khongtontai_xyz" } });
    expect(screen.getByText(/Không tìm thấy/i)).toBeTruthy();
  });

  it("gọi onClose khi bấm nút đóng", () => {
    let closed = false;
    render(<LabReference open onClose={() => (closed = true)} />);
    fireEvent.click(screen.getByTitle("Đóng"));
    expect(closed).toBe(true);
  });
});
