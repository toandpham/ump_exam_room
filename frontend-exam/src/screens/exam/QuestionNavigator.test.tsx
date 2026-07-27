import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import QuestionNavigator from "./QuestionNavigator";
import type { ExamQuestion } from "../../api/exam";

const questions: ExamQuestion[] = Array.from({ length: 5 }, (_, i) => ({
  id: `q${i}`, text: `Câu ${i}`, images: [], options: [],
}));

const noop = () => {};

describe("QuestionNavigator", () => {
  it("renders a button per question and the progress count", () => {
    const { container, getByText, getByRole } = render(
      <QuestionNavigator questions={questions} answers={{ q0: "A", q2: "B" }}
        current={0} total={5} answeredCount={2} unansweredCount={3}
        flags={{}} flaggedCount={0} onSelect={noop} onJumpUnanswered={noop} onJumpFlagged={noop} />,
    );
    expect(getByText("Đã làm 2/5")).toBeTruthy();
    // 5 numbered buttons (query by role so the "3" badge on the jump button
    // doesn't collide with the grid button "3").
    for (let i = 1; i <= 5; i++) expect(getByRole("button", { name: String(i) })).toBeTruthy();
    expect(container.textContent).toContain("Chưa làm");
  });

  it("selects by index when a number is clicked", () => {
    const onSelect = vi.fn();
    const { getByRole } = render(
      <QuestionNavigator questions={questions} answers={{}}
        current={0} total={5} answeredCount={0} unansweredCount={5}
        flags={{}} flaggedCount={0} onSelect={onSelect} onJumpUnanswered={noop} onJumpFlagged={noop} />,
    );
    getByRole("button", { name: "3" }).click();
    expect(onSelect).toHaveBeenCalledWith(2);   // button "3" → index 2
  });

  it("shows the all-done banner when nothing is unanswered", () => {
    const { container } = render(
      <QuestionNavigator questions={questions} answers={{}}
        current={0} total={5} answeredCount={5} unansweredCount={0}
        flags={{}} flaggedCount={0} onSelect={noop} onJumpUnanswered={noop} onJumpFlagged={noop} />,
    );
    expect(container.textContent).toContain("Đã trả lời hết");
  });

  // ── Cờ "cần xem lại" (27-07) — chỉ lưu trên máy, giám thị không thấy ──
  it("không có câu nào đánh dấu thì KHÔNG hiện nút nhảy", () => {
    // Kiểm đích danh NÚT (theo title) — chữ "Cần xem lại" vẫn còn ở phần chú giải
    // màu, vốn luôn hiện để thí sinh biết có tính năng này.
    const { queryByTitle } = render(
      <QuestionNavigator questions={questions} answers={{}} flags={{}}
        current={0} total={5} answeredCount={0} unansweredCount={5} flaggedCount={0}
        onSelect={noop} onJumpUnanswered={noop} onJumpFlagged={noop} />,
    );
    expect(queryByTitle("Nhảy tới câu kế tiếp đã đánh dấu xem lại")).toBeNull();
  });

  it("hiện nút kèm SỐ câu đã đánh dấu và gọi onJumpFlagged khi bấm", () => {
    const onJumpFlagged = vi.fn();
    const { getByTitle, container } = render(
      <QuestionNavigator questions={questions} answers={{}} flags={{ q1: true, q3: true }}
        current={0} total={5} answeredCount={0} unansweredCount={5} flaggedCount={2}
        onSelect={noop} onJumpUnanswered={noop} onJumpFlagged={onJumpFlagged} />,
    );
    expect(container.textContent).toContain("Cần xem lại");
    getByTitle("Nhảy tới câu kế tiếp đã đánh dấu xem lại").click();
    expect(onJumpFlagged).toHaveBeenCalled();
  });

  it("chỉ ô số của câu ĐƯỢC đánh dấu mới có chấm", () => {
    const { queryByTestId, getByTestId } = render(
      <QuestionNavigator questions={questions} answers={{}} flags={{ q1: true }}
        current={0} total={5} answeredCount={0} unansweredCount={5} flaggedCount={1}
        onSelect={noop} onJumpUnanswered={noop} onJumpFlagged={noop} />,
    );
    expect(queryByTestId("flagdot-0")).toBeNull();
    expect(getByTestId("flagdot-1")).toBeTruthy();
  });

  it("câu ĐÃ trả lời vẫn đánh dấu được — chấm không làm mất màu 'đã làm'", () => {
    const { getByTestId } = render(
      <QuestionNavigator questions={questions} answers={{ q1: "A" }} flags={{ q1: true }}
        current={0} total={5} answeredCount={1} unansweredCount={4} flaggedCount={1}
        onSelect={noop} onJumpUnanswered={noop} onJumpFlagged={noop} />,
    );
    expect(getByTestId("flagdot-1").parentElement!.className).toContain("bg-green-600");
  });
});
