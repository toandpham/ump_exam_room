import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import IdentityInput, { sanitizeId, validateId, ID_ERROR } from "./IdentityInput";

describe("identity helpers", () => {
  it("sanitizes CCCD to digits only", () => {
    expect(sanitizeId("cccd", "01a2-3 4b")).toBe("01234");
  });
  it("sanitizes passport to uppercase alphanumerics", () => {
    expect(sanitizeId("passport", "ab12-34!")).toBe("AB1234");
  });
  it("validates CCCD = exactly 12 digits", () => {
    expect(validateId("cccd", "012345678901")).toBe(true);
    expect(validateId("cccd", "0123")).toBe(false);
    expect(validateId("cccd", "01234567890A")).toBe(false);
  });
  it("validates passport = 6–9 alphanumerics", () => {
    expect(validateId("passport", "AB1234")).toBe(true);
    expect(validateId("passport", "AB123456789")).toBe(false);
    expect(validateId("passport", "AB12")).toBe(false);
  });
  it("exposes per-type error messages", () => {
    expect(ID_ERROR.cccd).toMatch(/12/);
    expect(ID_ERROR.passport).toMatch(/hộ chiếu/i);
  });
});

describe("<IdentityInput>", () => {
  it("renders both type toggles and emits sanitized values", () => {
    const onValueChange = vi.fn();
    render(
      <IdentityInput
        variant="login"
        idType="cccd"
        value=""
        onIdTypeChange={() => {}}
        onValueChange={onValueChange}
      />,
    );
    expect(screen.getByText("CCCD")).toBeTruthy();
    expect(screen.getByText("Hộ chiếu")).toBeTruthy();
    const input = screen.getByPlaceholderText("Số CCCD (12 số)") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "12a34" } });
    expect(onValueChange).toHaveBeenCalledWith("1234");
  });

  it("switches type via the toggle", () => {
    const onIdTypeChange = vi.fn();
    render(
      <IdentityInput
        variant="register"
        idType="cccd"
        value=""
        onIdTypeChange={onIdTypeChange}
        onValueChange={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("Hộ chiếu"));
    expect(onIdTypeChange).toHaveBeenCalledWith("passport");
  });
});
