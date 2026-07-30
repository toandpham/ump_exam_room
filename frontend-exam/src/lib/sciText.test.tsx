import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { sciText } from "./sciText";

/** Máy thi chạy Win7: font hệ thống KHÔNG có glyph cho khối Unicode U+2070
 * (⁹ ⁺ ⁻ ₂ ₃…) nên chúng hiện thành ô vuông — đúng lỗi "số mũ bị lỗi" ở bảng
 * Tham chiếu xét nghiệm. Chữ số ASCII trong thẻ <sup>/<sub> thì font nào cũng có. */
const shown = (node: React.ReactNode) => render(<span>{node}</span>).container;

describe("sciText", () => {
  it("đổi số mũ Unicode thành <sup> với chữ số thường", () => {
    const c = shown(sciText("10⁹/L"));
    expect(c.querySelector("sup")?.textContent).toBe("9");
    expect(c.textContent).toBe("109/L");        // không còn ký tự lạ
    expect(c.textContent).not.toMatch(/[⁰-⁹]/);
  });

  it("đổi chỉ số dưới Unicode thành <sub>", () => {
    const c = shown(sciText("HCO₃⁻"));
    expect(c.querySelector("sub")?.textContent).toBe("3");
    expect(c.querySelector("sup")?.textContent).toBe("-");
    expect(c.textContent).toBe("HCO3-");
  });

  it("gộp các ký tự mũ liền nhau vào MỘT thẻ (10¹² chứ không phải 10¹ rồi ²)", () => {
    const c = shown(sciText("10¹²/L"));
    expect(c.querySelectorAll("sup").length).toBe(1);
    expect(c.querySelector("sup")?.textContent).toBe("12");
  });

  it("giữ nguyên phần chữ thường + dấu cộng của ion", () => {
    const c = shown(sciText("Ca²⁺"));
    expect(c.textContent).toBe("Ca2+");
    expect(c.querySelector("sup")?.textContent).toBe("2+");
  });

  it("chuỗi không có số mũ thì trả về y nguyên", () => {
    const c = shown(sciText("Creatinin"));
    expect(c.textContent).toBe("Creatinin");
    expect(c.querySelector("sup")).toBeNull();
  });

  it("giữ xuống dòng (ô Tham chiếu dùng whitespace-pre-line)", () => {
    const c = shown(sciText("Nam: 4,5-5,9\nNữ: 4,1-5,1"));
    expect(c.textContent).toBe("Nam: 4,5-5,9\nNữ: 4,1-5,1");
  });

  it("BẢNG DỮ LIỆU THẬT không còn ký tự ngoài Latin-1 sau khi render", async () => {
    // Chốt chặn: nếu sau này ai thêm dòng mới dùng ⁹/₂ mà quên bọc sciText thì
    // test này đỏ ngay, không phải chờ tới ngày thi mới phát hiện.
    const { LAB_GROUPS, LAB_NOTES } = await import("./labReference");
    const risky = /[⁰-₟]/;
    for (const g of LAB_GROUPS) {
      for (const r of g.rows) {
        for (const s of [r.test, r.unit, r.ref]) {
          expect(shown(sciText(s)).textContent).not.toMatch(risky);
        }
      }
    }
    for (const n of LAB_NOTES) expect(shown(sciText(n)).textContent).not.toMatch(risky);
  });
});
