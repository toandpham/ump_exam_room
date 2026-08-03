import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
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
        flagged={false} onToggleFlag={noop} onSelect={noop} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
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
        flagged={false} onToggleFlag={noop} onSelect={onSelect} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    getByText("Đà Nẵng").click();
    expect(onSelect).toHaveBeenCalledWith("q1", "C");
  });

  it("shows 'Nộp bài' on the last question and 'Câu sau' otherwise", () => {
    const last = render(
      <QuestionCard q={Q} index={0} total={1} answers={{}} unansweredCount={0}
        flagged={false} onToggleFlag={noop} onSelect={noop} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    expect(last.container.textContent).toContain("Nộp bài");

    const mid = render(
      <QuestionCard q={Q} index={0} total={5} answers={{}} unansweredCount={0}
        flagged={false} onToggleFlag={noop} onSelect={noop} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    expect(mid.container.textContent).toContain("Câu sau");
  });

  it("AD-107: hiển thị bản NHỎ (thumb), bấm phóng to mới dùng bản đầy đủ", () => {
    const q: ExamQuestion = {
      ...Q,
      images: ["/uploads/full.jpg"],
      blocks: [{ type: "image", src: "/uploads/full.jpg", thumb: "/uploads/full_t.jpg" }],
    };
    const { container } = render(
      <QuestionCard q={q} index={0} total={1} answers={{}} unansweredCount={0}
        flagged={false} onToggleFlag={noop} onSelect={noop} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    const inline = container.querySelector("img")!;
    expect(inline.getAttribute("src")).toBe("/uploads/full_t.jpg");   // trong bài: bản nhỏ
    fireEvent.click(inline);                                          // phóng to
    // AD-109: lightbox lũy tiến — bản nhỏ hiện NGAY, bản đầy đủ đè lên khi tải xong.
    const zoomed = Array.from(container.querySelectorAll(".fixed.inset-0 img"))
      .map((el) => el.getAttribute("src"));
    expect(zoomed).toEqual(["/uploads/full_t.jpg", "/uploads/full.jpg"]);
  });

  it("AD-98: render khối theo ĐÚNG thứ tự file (chữ → ảnh → câu hỏi)", () => {
    const q: ExamQuestion = {
      ...Q, text: "Xét nghiệm.\nChẩn đoán nào?", images: ["/uploads/x.jpg"],
      blocks: [
        { type: "text", src: "", text: "Xét nghiệm cận lâm sàng." },
        { type: "image", src: "/uploads/x.jpg" },
        { type: "text", src: "", text: "Chẩn đoán nào sau đây?" },
      ],
    };
    const { container } = render(
      <QuestionCard q={q} index={0} total={1} answers={{}} unansweredCount={0}
        flagged={false} onToggleFlag={noop} onSelect={noop} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    // Ảnh phải nằm GIỮA hai đoạn chữ (không dồn xuống cuối).
    const nodes = Array.from(container.querySelectorAll("p, img"));
    const kinds = nodes
      .filter((n) => n.tagName === "IMG" || (n.textContent || "").includes("nghiệm") || (n.textContent || "").includes("Chẩn đoán nào sau"))
      .map((n) => (n.tagName === "IMG" ? "img" : "text"));
    expect(kinds).toEqual(["text", "img", "text"]);
  });

  // ── Cờ "cần xem lại" (27-07) ──
  it("bấm nút đánh dấu thì báo đúng mã câu", () => {
    const onToggleFlag = vi.fn();
    const { getByTitle } = render(
      <QuestionCard q={Q} index={0} total={1} answers={{}} unansweredCount={0}
        flagged={false} onToggleFlag={onToggleFlag}
        onSelect={noop} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    getByTitle("Đánh dấu để xem lại sau").click();
    expect(onToggleFlag).toHaveBeenCalledWith("q1");
  });

  it("đang đánh dấu thì nút đổi nhãn để bỏ đánh dấu", () => {
    const { container, getByTitle } = render(
      <QuestionCard q={Q} index={0} total={1} answers={{}} unansweredCount={0}
        flagged={true} onToggleFlag={noop}
        onSelect={noop} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    expect(container.textContent).toContain("Đã đánh dấu");
    expect(getByTitle("Bỏ đánh dấu câu này")).toBeTruthy();
  });
});

// AD-127: số mũ trong đề phải render bằng <sup>/<sub> chữ số ASCII. Ký tự Unicode
// ⁹ ₃ ⁻ không có glyph trong font Windows 7 (máy thi) → để nguyên là ra ô vuông.
describe("QuestionCard — số mũ / chỉ số dưới", () => {
  const supQ: ExamQuestion = {
    ...Q,
    text: "Bạch cầu 12.5 x 10⁹/L, HCO₃⁻ 18 mmol/L?",
    options: [
      { id: "A", text: "10¹²/L", images: [] },
      { id: "B", text: "Bình thường", images: [] },
      { id: "C", text: "Thấp", images: [] },
      { id: "D", text: "Cao", images: [] },
    ],
  };

  it("renders exponents in the stem as <sup>/<sub> with ASCII digits", () => {
    const { container } = render(
      <QuestionCard q={supQ} index={0} total={1} answers={{}} unansweredCount={0}
        flagged={false} onToggleFlag={noop} onSelect={noop} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    expect(container.querySelector("sup")?.textContent).toBe("9");
    expect(container.querySelector("sub")?.textContent).toBe("3");
    // Ký tự Unicode gốc KHÔNG được lọt ra DOM (Win7 hiện ô vuông).
    expect(container.textContent).not.toContain("⁹");
    expect(container.textContent).not.toContain("₃");
  });

  it("renders exponents in option text too", () => {
    const { container } = render(
      <QuestionCard q={supQ} index={0} total={1} answers={{}} unansweredCount={0}
        flagged={false} onToggleFlag={noop} onSelect={noop} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    const sups = [...container.querySelectorAll("sup")].map((s) => s.textContent);
    expect(sups).toContain("12");
    expect(container.textContent).not.toContain("¹²");
  });

  it("renders exponents inside ordered blocks (đề nạp mới)", () => {
    const blockQ: ExamQuestion = {
      ...Q, text: "", blocks: [{ type: "text", text: "Tiểu cầu 250 x 10⁹/L" }],
    };
    const { container } = render(
      <QuestionCard q={blockQ} index={0} total={1} answers={{}} unansweredCount={0}
        flagged={false} onToggleFlag={noop} onSelect={noop} onPrev={noop} onNext={noop} onJumpUnanswered={noop} onSubmit={noop} />,
    );
    expect(container.querySelector("sup")?.textContent).toBe("9");
  });
});
