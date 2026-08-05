import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import ImageLightbox from "./ImageLightbox";

const setup = (over: Partial<React.ComponentProps<typeof ImageLightbox>> = {}) => {
  const onClose = vi.fn();
  const r = render(
    <ImageLightbox full="/full.jpg" thumb="/thumb.jpg" onClose={onClose} {...over} />,
  );
  const box = r.container.querySelector('img[src="/thumb.jpg"]')!.parentElement as HTMLElement;
  return { ...r, onClose, box };
};

/** Khung ảnh phải đo theo MÀN HÌNH; đây chính là chỗ bản cũ sai (dùng % của một
 * hàng lưới tự co theo nội dung) khiến ảnh lớn tràn ra ngoài màn hình. */
describe("ImageLightbox — không tràn màn hình", () => {
  it("giới hạn ảnh theo đơn vị màn hình, không theo phần trăm khung cha", () => {
    const { container } = setup();
    const img = container.querySelector('img[src="/thumb.jpg"]')!;
    expect(img.className).toContain("max-h-[82vh]");
    expect(img.className).toContain("max-w-[92vw]");
  });

  it("khung ngoài cắt phần thừa để ảnh phóng to không đè ra ngoài", () => {
    const { container } = setup();
    expect(container.querySelector(".overflow-hidden")).toBeTruthy();
  });
});

describe("ImageLightbox — phóng to nhiều cấp", () => {
  it("bắt đầu ở 100% và tăng dần qua các mức", () => {
    const { getByText, getByLabelText } = setup();
    expect(getByText("100%")).toBeTruthy();
    fireEvent.click(getByLabelText("Phóng to"));
    expect(getByText("150%")).toBeTruthy();
    fireEvent.click(getByLabelText("Phóng to"));
    expect(getByText("200%")).toBeTruthy();
  });

  it("thu nhỏ quay lại được và khoá ở hai đầu", () => {
    const { getByText, getByLabelText } = setup();
    expect((getByLabelText("Thu nhỏ") as HTMLButtonElement).disabled).toBe(true);
    for (let i = 0; i < 10; i++) fireEvent.click(getByLabelText("Phóng to"));
    expect(getByText("400%")).toBeTruthy();          // không vượt mức cao nhất
    expect((getByLabelText("Phóng to") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(getByLabelText("Thu nhỏ"));
    expect(getByText("300%")).toBeTruthy();
  });

  it("bấm đúp để phóng to rồi trả về 100%", () => {
    const { getByText, box } = setup();
    fireEvent.doubleClick(box);
    expect(getByText("200%")).toBeTruthy();
    fireEvent.doubleClick(box);
    expect(getByText("100%")).toBeTruthy();
  });

  it("áp tỉ lệ bằng transform (nhẹ cho máy yếu)", () => {
    const { getByLabelText, box } = setup();
    fireEvent.click(getByLabelText("Phóng to"));
    expect(box.style.transform).toContain("scale(1.5)");
  });
});

describe("ImageLightbox — kéo để xem vùng cần", () => {
  it("chưa phóng to thì kéo không xê dịch", () => {
    const { box } = setup();
    fireEvent.pointerDown(box, { clientX: 0, clientY: 0 });
    fireEvent.pointerMove(box, { clientX: 80, clientY: 40 });
    expect(box.style.transform).toContain("translate(0px, 0px)");
  });

  it("chỉ hiện gợi ý kéo khi đã phóng to", () => {
    const { queryByText, getByLabelText } = setup();
    expect(queryByText(/Kéo ảnh để xem/)).toBeNull();
    fireEvent.click(getByLabelText("Phóng to"));
    expect(queryByText(/Kéo ảnh để xem/)).toBeTruthy();
  });
});

describe("ImageLightbox — đóng", () => {
  it("có nút Đóng (bắt buộc: phần mềm thi chặn phím Esc)", () => {
    const { getByLabelText, onClose } = setup();
    fireEvent.click(getByLabelText("Đóng ảnh"));
    expect(onClose).toHaveBeenCalled();
  });

  it("bấm nền thì đóng, nhưng bấm vào ảnh thì không", () => {
    const { container, box, onClose } = setup();
    fireEvent.click(box);
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(container.firstChild as Element);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("kéo ảnh rồi thả tay ra NỀN không được đóng mất ảnh", () => {
    // Tình huống thật: kéo mạnh thì con trỏ ra khỏi ảnh, thả tay trên nền → sự
    // kiện bấm rơi vào NỀN. Không có cờ "đã kéo" thì ảnh bị đóng oan.
    const { container, getByLabelText, box, onClose } = setup();
    fireEvent.click(getByLabelText("Phóng to"));
    fireEvent.pointerDown(box, { clientX: 10, clientY: 10 });
    fireEvent.pointerMove(box, { clientX: 90, clientY: 60 });
    fireEvent.click(container.firstChild as Element);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("bấm thanh phóng to không làm đóng ảnh", () => {
    const { getByLabelText, onClose } = setup();
    fireEvent.click(getByLabelText("Phóng to"));
    expect(onClose).not.toHaveBeenCalled();
  });
});
