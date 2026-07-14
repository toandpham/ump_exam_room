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
        onSelect={noop} onJumpUnanswered={noop} />,
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
        onSelect={onSelect} onJumpUnanswered={noop} />,
    );
    getByRole("button", { name: "3" }).click();
    expect(onSelect).toHaveBeenCalledWith(2);   // button "3" → index 2
  });

  it("shows the all-done banner when nothing is unanswered", () => {
    const { container } = render(
      <QuestionNavigator questions={questions} answers={{}}
        current={0} total={5} answeredCount={5} unansweredCount={0}
        onSelect={noop} onJumpUnanswered={noop} />,
    );
    expect(container.textContent).toContain("Đã trả lời hết");
  });
});
