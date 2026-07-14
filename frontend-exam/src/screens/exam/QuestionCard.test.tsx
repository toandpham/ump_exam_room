import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import QuestionCard from "./QuestionCard";
import type { ExamQuestion } from "../../api/exam";

const Q: ExamQuestion = {
  id: "q1",
  text: "Thủ đô Việt Nam?",
  images: [],
  options: [
    { id: "A", text: "Hà Nội", images: [] },
    { id: "B", text: "TP.HCM", images: [] },
    { id: "C", text: "Đà Nẵng", images: [] },
    { id: "D", text: "Huế", images: [] },
  ],
};

const noop = () => {};

describe("QuestionCard", () => {
  it("renders the stem, positional A–D labels and option text", () => {
    const { container, getByText } = render(
      <QuestionCard q={Q} index={0} total={10} answers={{}} unansweredCount={3}
        onSelect={noop} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    expect(container.textContent).toContain("Thủ đô Việt Nam?");
    expect(container.textContent).toContain("Câu 1/10");
    ["A", "B", "C", "D"].forEach((l) => expect(getByText(l)).toBeTruthy());
    expect(getByText("Hà Nội")).toBeTruthy();
  });

  it("submits the option's stable id (not the positional label) on click", () => {
    const onSelect = vi.fn();
    const { getByText } = render(
      <QuestionCard q={Q} index={0} total={1} answers={{}} unansweredCount={0}
        onSelect={onSelect} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    getByText("Đà Nẵng").click();
    expect(onSelect).toHaveBeenCalledWith("q1", "C");
  });

  it("shows 'Nộp bài' on the last question and 'Câu sau' otherwise", () => {
    const last = render(
      <QuestionCard q={Q} index={0} total={1} answers={{}} unansweredCount={0}
        onSelect={noop} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    expect(last.container.textContent).toContain("Nộp bài");

    const mid = render(
      <QuestionCard q={Q} index={0} total={5} answers={{}} unansweredCount={0}
        onSelect={noop} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    expect(mid.container.textContent).toContain("Câu sau");
  });
});
