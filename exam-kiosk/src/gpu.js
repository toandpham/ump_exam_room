"use strict";
// Quyết định BẬT/TẮT tăng tốc GPU cho từng máy (AD-95) — tách khỏi main.js ở
// refactor đợt 3 để logic này test được THẬT (trước đây chỉ "phủ" bằng grep chuỗi).
// KHÔNG import electron ở đây.
//
// TRƯỚC ĐÂY (AD-66) tắt cứng GPU → Chromium vẽ MỌI THỨ bằng CPU (SwiftShader).
// Trên máy thi yếu (Win7/4GB) đây là nguyên nhân GIẬT LAG chính: cùng máy đó
// Chrome (bật GPU) chạy mượt, kiosk (tắt GPU) thì ì ạch. Lý do tắt ngày xưa là
// MỘT SỐ máy Win10 driver cũ crash lúc khởi tạo Direct3D (0x80000003) — không phải
// tất cả. Nên nay: BẬT GPU mặc định (mượt), kèm cơ chế TỰ DÒ — máy nào crash vì
// GPU thì tự tắt cho RIÊNG máy đó ở các lần chạy sau, không cần IT đụng tay.
//
// Cơ chế tự dò (self-heal): ghi cờ "đang thử GPU" TRƯỚC khi mở cửa sổ; xoá khi
// cửa sổ hiển thị được lần đầu. Lần khởi động sau còn thấy cờ đó (lần trước chết
// trước khi kịp hiển thị) → kết luận GPU hỏng → ghi cờ "GPU off" vĩnh viễn.

/**
 * Quyết định thuần (không I/O) — dễ test:
 *   @param {{configDisable:boolean, offFlag:boolean, probeFlag:boolean}} state
 *   @returns {{disable:boolean, reason:string, markBad:boolean, writeProbe:boolean}}
 */
function decideGpu(state) {
  const { configDisable, offFlag, probeFlag } = state || {};
  if (configDisable) {
    return { disable: true, reason: "cấu hình disableGpu=true", markBad: false, writeProbe: false };
  }
  if (offFlag) {
    return {
      disable: true, reason: "máy này từng crash GPU — đã đánh dấu tắt",
      markBad: false, writeProbe: false,
    };
  }
  if (probeFlag) {
    // Lần thử GPU trước KHÔNG hoàn tất (app chết trước khi cửa sổ hiện) → GPU hỏng.
    return {
      disable: true, reason: "lần thử GPU trước bị crash — chuyển hẳn sang CPU",
      markBad: true, writeProbe: false,
    };
  }
  // Để GPU BẬT (mặc định Electron). Ghi cờ thử; sẽ xoá khi cửa sổ hiện được.
  return { disable: false, reason: "", markBad: false, writeProbe: true };
}

module.exports = { decideGpu };
