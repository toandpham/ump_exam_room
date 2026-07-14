import { describe, it, expect, vi } from "vitest";
import { useState } from "react";
import { render, fireEvent } from "@testing-library/react";
import { CreateWizard } from "./ExamsPage";
import type { SectionCreate } from "../api/exams";

const INITIAL: SectionCreate = {
  name: "",
  description: "",
  duration_minutes: 45,
  exam_date: null,
  allow_registration: false,
  room_count: 1,
  room_capacity: 0,
  sittings: [{ name: "Buổi 1", scheduled_date: null, duration_minutes: null }],
};

/** Stateful harness so setForm actually drives the controlled inputs, and the
 *  test can read back the resulting form via formRef (what would be POSTed). */
function Harness({ onSubmit = () => {}, formRef }: {
  onSubmit?: () => void;
  formRef?: { current: SectionCreate };
}) {
  const [form, setForm] = useState<SectionCreate>(INITIAL);
  if (formRef) formRef.current = form;
  return <CreateWizard form={form} setForm={setForm} onSubmit={onSubmit} submitting={false} error="" />;
}

describe("CreateWizard (tạo kỳ thi — khai báo cấu trúc)", () => {
  it("hiển thị đủ các trường cấu trúc của quy trình mới", () => {
    const { container, getByText } = render(<Harness />);
    const txt = container.textContent ?? "";
    expect(txt).toContain("Tên kỳ thi");
    expect(txt).toContain("Số phòng thi");
    expect(txt).toContain("Sức chứa mỗi phòng");
    expect(txt).toContain("Buổi thi");
    expect(txt).toContain("Cho phép thí sinh đăng ký tại chỗ"); // self-register (AD-33)
    expect(getByText("Thêm buổi")).toBeTruthy();
  });

  it("nút Tạo bị khoá khi chưa nhập tên, mở khoá sau khi nhập", () => {
    const { getByPlaceholderText, getByRole } = render(<Harness />);
    const submit = getByRole("button", { name: /Tạo kỳ thi/ }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.change(getByPlaceholderText("VD: Kỳ thi thử quốc gia lần 1"),
      { target: { value: "Kỳ thi thử lần 1" } });
    expect(submit.disabled).toBe(false);
  });

  it("Thêm/xoá buổi cập nhật danh sách + nhãn nút phản ánh số phòng·buổi", () => {
    const { getByText, getByRole, getAllByRole } = render(<Harness />);
    // Ban đầu: 1 phòng · 1 buổi, nút xoá buổi bị khoá (không xoá buổi cuối).
    expect(getByRole("button", { name: /Tạo kỳ thi \(1 phòng · 1 buổi\)/ })).toBeTruthy();

    fireEvent.click(getByText("Thêm buổi"));
    expect(getByRole("button", { name: /Tạo kỳ thi \(1 phòng · 2 buổi\)/ })).toBeTruthy();
    // Có 2 ô tên buổi giờ đây.
    expect(getAllByRole("textbox").filter((el) =>
      (el as HTMLInputElement).placeholder.startsWith("Tên buổi")).length).toBe(2);
  });

  it("không cho xoá buổi cuối cùng (luôn ≥ 1 buổi)", () => {
    const { container } = render(<Harness />);
    const removeBtns = Array.from(container.querySelectorAll("button[title='Xoá buổi']"));
    expect(removeBtns.length).toBe(1);
    expect((removeBtns[0] as HTMLButtonElement).disabled).toBe(true);
  });

  it("đổi số phòng → form gửi đi đúng payload cấu trúc", () => {
    const formRef = { current: INITIAL };
    const { getByPlaceholderText, getByDisplayValue, getByRole } =
      render(<Harness formRef={formRef} />);

    fireEvent.change(getByPlaceholderText("VD: Kỳ thi thử quốc gia lần 1"),
      { target: { value: "Kỳ thi A" } });
    // Số phòng thi (input number có value mặc định "1" — duy nhất).
    fireEvent.change(getByDisplayValue("1"), { target: { value: "3" } });

    expect(formRef.current.name).toBe("Kỳ thi A");
    expect(formRef.current.room_count).toBe(3);
    expect(formRef.current.allow_registration).toBe(false); // mặc định TẮT
    // Nhãn nút cập nhật theo số phòng.
    expect(getByRole("button", { name: /Tạo kỳ thi \(3 phòng · 1 buổi\)/ })).toBeTruthy();
  });

  it("ô số: xóa trống được (không kẹt số ở đầu) + gõ số mới tự do", () => {
    const formRef = { current: INITIAL };
    const { getByDisplayValue } = render(<Harness formRef={formRef} />);
    const roomInput = getByDisplayValue("1") as HTMLInputElement; // số phòng = 1
    // Xóa sạch → ô trống thật sự (trước đây bị kẹt lại "1").
    fireEvent.change(roomInput, { target: { value: "" } });
    expect(roomInput.value).toBe("");
    // Gõ số mới.
    fireEvent.change(roomInput, { target: { value: "12" } });
    expect(roomInput.value).toBe("12");
    expect(formRef.current.room_count).toBe(12);
  });

  it("ô số: để trống rồi rời ô → tự về giá trị mặc định (fallback)", () => {
    const formRef = { current: INITIAL };
    const { getByDisplayValue } = render(<Harness formRef={formRef} />);
    const roomInput = getByDisplayValue("1") as HTMLInputElement;
    fireEvent.change(roomInput, { target: { value: "" } });
    fireEvent.blur(roomInput);
    expect(roomInput.value).toBe("1");        // fallback của số phòng
    expect(formRef.current.room_count).toBe(1);
  });

  it("ô số: vượt giới hạn thì chuẩn hóa khi rời ô (clamp về max)", () => {
    const formRef = { current: INITIAL };
    const { getByDisplayValue } = render(<Harness formRef={formRef} />);
    const roomInput = getByDisplayValue("1") as HTMLInputElement;
    fireEvent.change(roomInput, { target: { value: "99" } }); // max 50
    fireEvent.blur(roomInput);
    expect(roomInput.value).toBe("50");
    expect(formRef.current.room_count).toBe(50);
  });

  it("bấm Tạo gọi onSubmit khi hợp lệ", () => {
    const onSubmit = vi.fn();
    const { getByPlaceholderText, getByRole } = render(<Harness onSubmit={onSubmit} />);
    fireEvent.change(getByPlaceholderText("VD: Kỳ thi thử quốc gia lần 1"),
      { target: { value: "Kỳ thi B" } });
    fireEvent.click(getByRole("button", { name: /Tạo kỳ thi/ }));
    expect(onSubmit).toHaveBeenCalledOnce();
  });
});
