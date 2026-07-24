import { describe, it, expect, afterEach } from "vitest";
import { shouldLite, applyLiteMode } from "./lite";

describe("lite mode (AD-112)", () => {
  afterEach(() => {
    document.documentElement.classList.remove("lite");
    localStorage.clear();
  });

  it("tự bật khi máy ≤4GB RAM, giữ nguyên khi 8GB, không bật khi API vắng (Firefox)", () => {
    expect(shouldLite(4, null)).toBe(true);    // đội 320 máy Win7/4GB
    expect(shouldLite(2, null)).toBe(true);
    expect(shouldLite(8, null)).toBe(false);   // 80 máy Win10/8GB — giữ giao diện đầy đủ
    expect(shouldLite(undefined, null)).toBe(false);
  });

  it("override tay thắng auto-detect: exam_lite=1 ép bật, =0 ép tắt", () => {
    expect(shouldLite(8, "1")).toBe(true);
    expect(shouldLite(4, "0")).toBe(false);
  });

  it("applyLiteMode gắn class `lite` vào <html> khi thuộc diện", () => {
    localStorage.setItem("exam_lite", "1");
    expect(applyLiteMode()).toBe(true);
    expect(document.documentElement.classList.contains("lite")).toBe(true);
  });
});
