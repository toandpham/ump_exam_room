/** Nút "Báo lỗi câu hỏi" của thí sinh (đợt 3).
 *
 * Điều quan trọng nhất ở đây không phải giao diện mà là: gửi HỎNG thì thí sinh
 * phải BIẾT. Nuốt lỗi là em ấy tưởng đã báo, còn hội đồng không hề nhận được gì.
 */
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ReportQuestionButton from "./ReportQuestionButton";

const openBox = () => fireEvent.click(screen.getByText("Báo lỗi câu hỏi"));
const type = (v: string) =>
  fireEvent.change(screen.getByPlaceholderText("Nội dung báo lỗi…"), { target: { value: v } });

describe("ReportQuestionButton", () => {
  it("gửi nội dung kèm đúng số câu", async () => {
    const onSend = vi.fn(async () => {});
    render(<ReportQuestionButton questionNumber={47} onSend={onSend} />);
    openBox();
    expect(screen.getByText("Báo lỗi câu 47")).toBeTruthy();
    type("Thiếu hình chụp X-quang");
    fireEvent.click(screen.getByText("Gửi"));
    await waitFor(() => expect(onSend).toHaveBeenCalledWith("Thiếu hình chụp X-quang"));
    expect(await screen.findByText(/Đã gửi tới hội đồng/)).toBeTruthy();
  });

  it("gửi hỏng thì báo ngay tại chỗ, KHÔNG giả vờ đã gửi", async () => {
    const onSend = vi.fn(async () => { throw new Error("Mất kết nối máy chủ"); });
    render(<ReportQuestionButton questionNumber={3} onSend={onSend} />);
    openBox();
    type("Câu này sai đề");
    fireEvent.click(screen.getByText("Gửi"));
    expect(await screen.findByText("Mất kết nối máy chủ")).toBeTruthy();
    expect(screen.queryByText(/Đã gửi tới hội đồng/)).toBeNull();
  });

  it("nội dung trống thì không gửi", () => {
    const onSend = vi.fn(async () => {});
    render(<ReportQuestionButton questionNumber={1} onSend={onSend} />);
    openBox();
    type("  ");
    fireEvent.click(screen.getByText("Gửi"));
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByText(/Hãy mô tả ngắn gọn/)).toBeTruthy();
  });

  it("huỷ thì đóng hộp và không gửi gì", () => {
    const onSend = vi.fn(async () => {});
    render(<ReportQuestionButton questionNumber={1} onSend={onSend} />);
    openBox();
    type("abc def");
    fireEvent.click(screen.getByText("Huỷ"));
    expect(screen.queryByPlaceholderText("Nội dung báo lỗi…")).toBeNull();
    expect(onSend).not.toHaveBeenCalled();
  });
});
