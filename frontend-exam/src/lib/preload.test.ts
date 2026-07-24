import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

/** Ảnh giả: ghi lại URL được tải rồi báo "xong" ở tick kế (không đụng mạng thật). */
const loaded: string[] = [];
class FakeImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private _src = "";
  set src(v: string) {
    this._src = v;
    loaded.push(v);
    setTimeout(() => this.onload?.(), 0);
  }
  get src() { return this._src; }
}

/** Module giữ sổ `seen` ở phạm vi module → mỗi test nạp lại cho sạch. */
async function freshModule() {
  vi.resetModules();
  return await import("./preload");
}

beforeEach(() => {
  loaded.length = 0;
  (globalThis as any).Image = FakeImage as unknown as typeof Image;
  vi.useFakeTimers();
  // Bỏ ngẫu nhiên để nhịp/độ trễ xuất phát thành xác định trong test.
  vi.spyOn(Math, "random").mockReturnValue(0);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("preloadImages (tải ngay vài câu quanh chỗ đang làm)", () => {
  it("tải hết các URL được đưa vào", async () => {
    const { preloadImages } = await freshModule();
    preloadImages(["a.jpg", "b.jpg", "c.jpg"]);
    await vi.advanceTimersByTimeAsync(50);
    expect(loaded.sort()).toEqual(["a.jpg", "b.jpg", "c.jpg"]);
  });

  it("KHÔNG tải lại ảnh đã tải ở lần gọi trước", async () => {
    const { preloadImages } = await freshModule();
    preloadImages(["a.jpg"]);
    await vi.advanceTimersByTimeAsync(50);
    preloadImages(["a.jpg", "b.jpg"]);
    await vi.advanceTimersByTimeAsync(50);
    expect(loaded).toEqual(["a.jpg", "b.jpg"]);
  });
});

describe("preloadAllPaced (nạp cả đề xuống cache đĩa, rải chậm)", () => {
  it("rải từng ảnh theo nhịp chứ không tải dồn một lúc", async () => {
    const { preloadAllPaced, PACE_MIN_MS } = await freshModule();
    preloadAllPaced(["1.jpg", "2.jpg", "3.jpg"]);

    await vi.advanceTimersByTimeAsync(10);          // qua độ trễ xuất phát (random=0)
    expect(loaded).toEqual(["1.jpg"]);               // mới đúng 1 ảnh — không dồn

    await vi.advanceTimersByTimeAsync(PACE_MIN_MS + 10);
    expect(loaded).toEqual(["1.jpg", "2.jpg"]);
    await vi.advanceTimersByTimeAsync(PACE_MIN_MS + 10);
    expect(loaded).toEqual(["1.jpg", "2.jpg", "3.jpg"]);
  });

  it("huỷ được giữa chừng (rời màn thi thì dừng tải)", async () => {
    const { preloadAllPaced, PACE_MIN_MS } = await freshModule();
    const cancel = preloadAllPaced(["1.jpg", "2.jpg", "3.jpg"]);
    await vi.advanceTimersByTimeAsync(10);
    expect(loaded).toEqual(["1.jpg"]);
    cancel();
    await vi.advanceTimersByTimeAsync(10 * PACE_MIN_MS);
    expect(loaded).toEqual(["1.jpg"]);               // không tải thêm sau khi huỷ
  });

  it("chạy lại (ready → đang thi) thì bỏ qua ảnh đã tải, không tải trùng", async () => {
    const { preloadAllPaced, PACE_MIN_MS } = await freshModule();
    const cancel = preloadAllPaced(["1.jpg", "2.jpg", "3.jpg"]);
    await vi.advanceTimersByTimeAsync(PACE_MIN_MS + 20);
    expect(loaded).toEqual(["1.jpg", "2.jpg"]);
    cancel();

    preloadAllPaced(["1.jpg", "2.jpg", "3.jpg"]);    // effect chạy lại
    await vi.advanceTimersByTimeAsync(10);
    expect(loaded).toEqual(["1.jpg", "2.jpg", "3.jpg"]);   // chỉ còn ảnh chưa tải
  });
});

describe("preloadAllFast (tải nhanh cả đề lúc chờ + tiến độ)", () => {
  it("tải hết và tiến độ chạm ĐÚNG total", async () => {
    const { preloadAllFast } = await freshModule();
    const seen: Array<[number, number]> = [];
    preloadAllFast(["a.jpg", "b.jpg", "c.jpg"], (d, t) => seen.push([d, t]));
    await vi.advanceTimersByTimeAsync(2000);
    expect(loaded.sort()).toEqual(["a.jpg", "b.jpg", "c.jpg"]);
    expect(seen[seen.length - 1]).toEqual([3, 3]);
  });

  it("BUG 34/37: ảnh bị luồng khác nẫng GIỮA CHỪNG vẫn được đếm — tiến độ chạm total", async () => {
    const { preloadImages, preloadAllFast } = await freshModule();
    // Kịch bản hiện trường: 2 luồng chạy SONG SONG lúc chờ. Luồng phụ đang tải
    // a,b và còn e xếp hàng; luồng tải-cả-đề khởi động cùng lúc...
    preloadImages(["a.jpg", "b.jpg", "e.jpg"]);   // concurrency 2 → a,b đang tải; e chờ
    let last: [number, number] | null = null;
    preloadAllFast(
      ["a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg", "f.jpg"],
      (d, t) => { last = [d, t]; },
    );
    // ...a tải xong → luồng phụ NẪNG e (sau khi luồng nhanh đã chốt sổ ban đầu).
    // Bản cũ: e bị bỏ-qua-không-đếm → kẹt 5/6 vĩnh viễn (= kẹt 34/37, nút Bắt đầu
    // thi không mở khoá). Bản vá: mỗi URL được ghé đúng 1 lần — tải hoặc "đã có
    // người tải" đều đếm → phải chạm 6/6.
    await vi.advanceTimersByTimeAsync(5000);
    expect(loaded.filter((u) => u === "e.jpg").length).toBe(1);   // không tải trùng
    expect(loaded.sort()).toEqual(["a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg", "f.jpg"]);
    expect(last).toEqual([6, 6]);
  });

  it("đề không có ảnh → báo 0/0 ngay (coi như tải xong)", async () => {
    const { preloadAllFast } = await freshModule();
    let last: [number, number] | null = null;
    preloadAllFast([], (d, t) => { last = [d, t]; });
    expect(last).toEqual([0, 0]);
  });
});

describe("imageUrlsOf", () => {
  it("gom ảnh của cả câu hỏi lẫn đáp án, đúng thứ tự", async () => {
    const { imageUrlsOf } = await freshModule();
    expect(imageUrlsOf([
      { images: ["q1.jpg"], options: [{ images: ["o1.jpg"] }, { images: [] }] },
      { images: [], options: [{ images: ["o2.jpg"] }] },
    ])).toEqual(["q1.jpg", "o1.jpg", "o2.jpg"]);
  });

  it("AD-107: ưu tiên bản nhỏ (thumbs) khi có — đó mới là thứ hiển thị trong bài", async () => {
    const { imageUrlsOf } = await freshModule();
    expect(imageUrlsOf([
      {
        images: ["q1.jpg", "q2.jpg"], thumbs: ["q1_t.jpg", "q2.jpg"],
        options: [{ images: ["o1.jpg"], thumbs: ["o1_t.jpg"] }],
      },
    ])).toEqual(["q1_t.jpg", "q2.jpg", "o1_t.jpg"]);
  });
});
