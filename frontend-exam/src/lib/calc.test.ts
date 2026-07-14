import { describe, it, expect } from "vitest";
import { evaluate, fmt } from "./calc";

describe("calc.evaluate", () => {
  it("does basic arithmetic", () => {
    expect(evaluate("1+2", "DEG")).toBe(3);
    expect(evaluate("10−4", "DEG")).toBe(6);   // dấu trừ Unicode từ bàn phím máy tính
    expect(evaluate("6÷2", "DEG")).toBe(3);
    expect(evaluate("3×4", "DEG")).toBe(12);
  });

  it("respects operator precedence", () => {
    expect(evaluate("2+3*4", "DEG")).toBe(14);
    expect(evaluate("2+3×4", "DEG")).toBe(14);
  });

  it("honours parentheses", () => {
    expect(evaluate("(2+3)*4", "DEG")).toBe(20);
  });

  it("evaluates degree-aware trig", () => {
    expect(evaluate("sin(30)", "DEG")).toBeCloseTo(0.5);
    expect(evaluate("cos(0)", "RAD")).toBe(1);
  });

  it("rejects disallowed input (safe-eval allowlist)", () => {
    expect(() => evaluate("alert(1)", "DEG")).toThrow();
    expect(() => evaluate("1;2", "DEG")).toThrow();
    expect(() => evaluate("globalThis", "DEG")).toThrow();
  });
});

describe("calc.fmt", () => {
  it("keeps integers plain", () => {
    expect(fmt(3)).toBe("3");
    expect(fmt(-12)).toBe("-12");
  });

  it("trims floating-point noise and trailing zeros", () => {
    expect(fmt(0.1 + 0.2)).toBe("0.3");
    expect(fmt(1.5)).toBe("1.5");
  });
});
