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
