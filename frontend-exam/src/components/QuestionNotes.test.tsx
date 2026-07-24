import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import QuestionNotes, { clearNotes } from "./QuestionNotes";

const SID = "sess-1";
const KEY = `exam_notes_${SID}`;

describe("QuestionNotes", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.useRealTimers());

  it("AD-111: gõ KHÔNG ghi đĩa từng phím — dồn nhịp rồi mới lưu (fix ì máy yếu)", () => {
    vi.useFakeTimers();
    render(
      <QuestionNotes open onClose={() => {}} sessionId={SID} questionId="q1" questionNumber={1} />,
    );
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "ghi chú câu 1" } });
    // Ngay sau phím gõ: CHƯA đụng đĩa (trước đây mỗi phím một cú ghi → khựng).
    expect(localStorage.getItem(KEY)).toBeNull();
    // Ngừng gõ ~0.8s → tự lưu.
    vi.advanceTimersByTime(1000);
    expect(JSON.parse(localStorage.getItem(KEY)!)).toEqual({ q1: "ghi chú câu 1" });
  });

  it("chuyển câu CHỐT ngay nháp câu trước + quay lại nạp đúng nháp cũ", () => {
    const { rerender } = render(
      <QuestionNotes open onClose={() => {}} sessionId={SID} questionId="q1" questionNumber={1} />,
    );
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "ghi chú câu 1" } });

    // đổi sang câu 2 → nháp câu 1 được chốt xuống đĩa NGAY (không chờ nhịp), ô trống
    rerender(<QuestionNotes open onClose={() => {}} sessionId={SID} questionId="q2" questionNumber={2} />);
    expect(JSON.parse(localStorage.getItem(KEY)!)).toEqual({ q1: "ghi chú câu 1" });
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "câu 2" } });

    // quay lại câu 1 → nạp đúng nháp cũ + nháp câu 2 cũng đã chốt
    rerender(<QuestionNotes open onClose={() => {}} sessionId={SID} questionId="q1" questionNumber={1} />);
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("ghi chú câu 1");
    expect(JSON.parse(localStorage.getItem(KEY)!)).toEqual({ q1: "ghi chú câu 1", q2: "câu 2" });
  });

  it("clearNotes xoá toàn bộ nháp của phiên", () => {
    localStorage.setItem(KEY, JSON.stringify({ q1: "x" }));
    clearNotes(SID);
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("không render khi đóng", () => {
    const { container } = render(
      <QuestionNotes open={false} onClose={() => {}} sessionId={SID} questionId="q1" questionNumber={1} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
