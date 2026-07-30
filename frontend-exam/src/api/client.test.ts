import { describe, it, expect } from "vitest";
import { api } from "./client";

describe("axios client (app thí sinh)", () => {
  it("R1: có timeout — cú gọi bị treo KHÔNG được kẹt vô hạn", () => {
    // Axios mặc định timeout=0 = chờ mãi. Khi đó một kết nối treo đúng lúc NỘP BÀI
    // sẽ không bao giờ kết thúc: không lỗi, không thử lại, `submittedRef` khoá luôn
    // → thí sinh tưởng đã nộp, bấm lại không được, và không rời phòng thi được.
    // Có timeout thì cú treo biến thành lỗi mạng → phần thử-lại + thông báo đỏ
    // trong useExamSession mới chạy tới.
    expect(api.defaults.timeout).toBeGreaterThan(0);
    // Đủ dài cho máy Win7 chậm tải đề, đủ ngắn để thí sinh không chờ vô nghĩa.
    expect(api.defaults.timeout).toBeLessThanOrEqual(30000);
  });
});
