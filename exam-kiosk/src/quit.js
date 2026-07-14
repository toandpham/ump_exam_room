"use strict";
// Lối thoát khẩn cấp (break-glass) — chỉ logic so khớp mật khẩu, thuần & test được.
// Việc thực thi (đóng app, khôi phục Task Manager) nằm ở main.js.
function checkEmergencyPassword(input, expected) {
  return typeof input === "string" && input.length > 0 && input === expected;
}

// Logic xử lý IPC verify mật khẩu khẩn cấp, tách riêng để test được (không cần Electron).
// Trả về { ok } và gọi onSuccess() khi đúng (main dùng để thoát app).
function handleEmergencyVerify(input, expected, onSuccess) {
  const ok = checkEmergencyPassword(input, expected);
  if (ok && typeof onSuccess === "function") onSuccess();
  return ok;
}

module.exports = { checkEmergencyPassword, handleEmergencyVerify };
