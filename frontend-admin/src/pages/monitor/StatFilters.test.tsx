import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import StatFilters from "./StatFilters";

const noop = () => {};

describe("StatFilters", () => {
  it("renders the labels + totals", () => {
    const { container } = render(
      <StatFilters counts={{ waiting: 2, in_progress: 3 }} assignedTotal={50}
        loggedIn={30} notLoggedIn={20} filter="all" setFilter={noop} />,
    );
    expect(container.textContent).toContain("Đã đăng ký");
    expect(container.textContent).toContain("50");
    expect(container.textContent).toContain("Đang làm");
  });

  it("không còn thẻ Đăng ký mới (đã gỡ — luồng phòng/Excel luôn = 0)", () => {
    const { container } = render(
      <StatFilters counts={{}} assignedTotal={40}
        loggedIn={30} notLoggedIn={5} filter="all" setFilter={noop} />,
    );
    expect(container.textContent).not.toContain("Đăng ký mới");
  });

  it("box 'Đã nộp' đếm cả timeout (hết-giờ-tự-nộp)", () => {
    // submitted=2 + timeout=3 → box "Đã nộp" hiện 5 (trước đây chỉ đếm submitted → 2).
    const { getByText } = render(
      <StatFilters counts={{ submitted: 2, timeout: 3 }} assignedTotal={10}
        loggedIn={5} notLoggedIn={0} filter="all" setFilter={noop} />,
    );
    const box = getByText("Đã nộp").closest("button")!;
    expect(box.textContent).toContain("5");
  });

  it("calls setFilter with the box key on click", () => {
    const setFilter = vi.fn();
    const { getByText } = render(
      <StatFilters counts={{}} assignedTotal={0}
        loggedIn={0} notLoggedIn={0} filter="all" setFilter={setFilter} />,
    );
    getByText("Đã đăng nhập").click();
    expect(setFilter).toHaveBeenCalledWith("logged_in");
  });

  it("không còn thẻ Vắng / Dự thi (đã gỡ — không đăng nhập = vắng)", () => {
    const { container } = render(
      <StatFilters counts={{}} assignedTotal={40}
        loggedIn={30} notLoggedIn={5} filter="all" setFilter={noop} />,
    );
    expect(container.textContent).not.toContain("Dự thi");
    // "Vắng" không còn là thẻ thống kê ở màn giám sát
    expect(container.textContent).not.toContain("Vắng");
  });

  it("thu bài: '✓ Đã thu đủ bài' khi submitted+timeout >= số đã đăng nhập", () => {
    // loggedIn=25; submitted=20 + timeout=5 = 25 >= 25
    const { container } = render(
      <StatFilters counts={{ submitted: 20, timeout: 5 }} assignedTotal={30}
        loggedIn={25} notLoggedIn={0} filter="all" setFilter={noop} />,
    );
    expect(container.textContent).toContain("Đã thu đủ bài");
  });

  it("thu bài: 'còn N bài chưa nộp' khi chưa thu đủ", () => {
    // loggedIn=25; submitted=10 → còn 15
    const { container } = render(
      <StatFilters counts={{ submitted: 10 }} assignedTotal={30}
        loggedIn={25} notLoggedIn={5} filter="all" setFilter={noop} />,
    );
    expect(container.textContent).toContain("15");
    expect(container.textContent).toContain("chưa nộp");
    expect(container.textContent).not.toContain("Đã thu đủ bài");
  });
});
