import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import QuestionNotes, { clearNotes } from "./QuestionNotes";

const SID = "sess-1";

describe("QuestionNotes", () => {
  beforeEach(() => localStorage.clear());

  it("lưu nháp theo từng câu vào localStorage", () => {
    const { rerender } = render(
      <QuestionNotes open onClose={() => {}} sessionId={SID} questionId="q1" questionNumber={1} />,
    );
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "ghi chú câu 1" } });
    expect(JSON.parse(localStorage.getItem(`exam_notes_${SID}`)!)).toEqual({ q1: "ghi chú câu 1" });

    // đổi sang câu 2 → ô trống; nhập nháp khác
    rerender(<QuestionNotes open onClose={() => {}} sessionId={SID} questionId="q2" questionNumber={2} />);
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "câu 2" } });
    expect(JSON.parse(localStorage.getItem(`exam_notes_${SID}`)!)).toEqual({ q1: "ghi chú câu 1", q2: "câu 2" });

    // quay lại câu 1 → nạp đúng nháp cũ
    rerender(<QuestionNotes open onClose={() => {}} sessionId={SID} questionId="q1" questionNumber={1} />);
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("ghi chú câu 1");
  });

  it("clearNotes xoá toàn bộ nháp của phiên", () => {
    localStorage.setItem(`exam_notes_${SID}`, JSON.stringify({ q1: "x" }));
    clearNotes(SID);
    expect(localStorage.getItem(`exam_notes_${SID}`)).toBeNull();
  });

  it("không render khi đóng", () => {
    const { container } = render(
      <QuestionNotes open={false} onClose={() => {}} sessionId={SID} questionId="q1" questionNumber={1} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
